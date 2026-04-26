"""
Asset validation (WK3 + v1.5 3D).

Build A policy: report-only (do not block UI work).
Build B policy: strict + attribution checks become failing gates.

v1.5: validates flat model files under assets/models/<category>/ (*.glb, *.gltf, *.obj)
instead of PNG frame sequences under assets/sprites/.

v1.6: optional `textures.files` in manifest — paths relative to `assets/` (e.g. `models/Models/Textures/floor_ground_grass.png`); missing file is an error.

This tool is intentionally FAST:
- no mesh decoding
- no image decoding
- only filesystem checks

WK30: validates `prefabs.buildings` JSON under assets/prefabs/buildings/ (manifest section).
Process exits non-zero if any finding has severity "error" (warnings never fail).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = PROJECT_ROOT / "tools" / "assets_manifest.json"
DEFAULT_ASSETS_ROOT = PROJECT_ROOT / "assets"

# Prefer glTF binary first; static meshes may use .obj.
MODEL_EXTS_ORDER = (".glb", ".gltf", ".obj")

# WK30: prefab JSON under assets/prefabs/buildings/<id>.json
PREFAB_BUILDING_REQUIRED_KEYS = frozenset(
    {"prefab_id", "building_type", "footprint_tiles", "ground_anchor_y", "pieces", "attribution"}
)
PREFAB_PIECE_REQUIRED_KEYS = frozenset({"model", "pos", "rot", "scale"})


@dataclass(frozen=True)
class Finding:
    severity: str  # "error" | "warn"
    code: str
    message: str
    path: str | None = None


def _load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("manifest must be a JSON object")
    return data


def _resolve_model_file(category_dir: Path, kind: str) -> tuple[Path | None, str | None]:
    """Return (path, ext) if assets/models/<category>/<kind>.{glb,gltf,obj} exists."""
    for stem in (kind, kind.lower()):
        for ext in MODEL_EXTS_ORDER:
            p = category_dir / f"{stem}{ext}"
            if p.is_file():
                return p, ext
    return None, None


def _validate_model_tree(
    *,
    assets_root: Path,
    category: str,
    kinds: Iterable[str],
    strict: bool,
) -> tuple[list[Finding], dict[str, Any]]:
    """
    Validate flat files under:
      assets/models/<category>/<kind>.glb|.gltf|.obj
    """
    findings: list[Finding] = []
    report: dict[str, Any] = {"category": category, "kinds": {}}

    base = assets_root / "models" / category
    if not base.exists():
        findings.append(
            Finding(
                "error",
                "missing_model_category_dir",
                f"Missing models directory for {category}",
                str(base),
            )
        )
        return findings, report

    if not base.is_dir():
        findings.append(
            Finding("error", "model_category_not_dir", f"Expected directory for {category}", str(base))
        )
        return findings, report

    for kind in kinds:
        resolved, ext = _resolve_model_file(base, kind)
        if resolved is not None:
            report["kinds"][kind] = {"file": resolved.name, "ext": ext, "ok": True}
        else:
            report["kinds"][kind] = {"file": None, "ok": False}
            findings.append(
                Finding(
                    "error" if strict else "warn",
                    "missing_model_file",
                    f"Missing model file for {category}:{kind} (expected {kind}.glb, .gltf, or .obj in {base})",
                    str(base),
                )
            )

    return findings, report


def _validate_texture_files(
    *,
    assets_root: Path,
    rel_paths: Iterable[str],
) -> tuple[list[Finding], dict[str, Any]]:
    """
    Validate files listed in manifest `textures.files` (paths relative to assets/ root).
    Used for world tiling albedo and other non-model PNGs (WK33+).
    """
    findings: list[Finding] = []
    report: dict[str, Any] = {"textures": {}}
    for rel in rel_paths:
        if not isinstance(rel, str) or not rel.strip():
            findings.append(Finding("error", "texture_path_invalid", f"Invalid texture entry: {rel!r}"))
            continue
        norm = rel.replace("\\", "/").strip().lstrip("/")
        if ".." in Path(norm).parts:
            findings.append(Finding("error", "texture_path_unsafe", f"Unsafe texture path: {rel!r}"))
            report["textures"][str(rel)] = {"ok": False}
            continue
        p = (assets_root / norm).resolve()
        ar = assets_root.resolve()
        try:
            p.relative_to(ar)
        except ValueError:
            findings.append(
                Finding("error", "texture_escapes_assets", f"Texture path escapes assets/: {rel}", str(p))
            )
            report["textures"][norm] = {"ok": False}
            continue
        ok = p.is_file()
        report["textures"][norm] = {"file": p.name if ok else None, "ok": ok}
        if not ok:
            findings.append(
                Finding(
                    "error",
                    "missing_texture_file",
                    f"Missing texture file: assets/{norm}",
                    str(p),
                )
            )
    return findings, report


def _validate_audio_tree(
    *,
    assets_root: Path,
    sfx_files: list[str] | None,
    ambient_files: Iterable[str],
    strict: bool,
) -> tuple[list[Finding], dict[str, Any]]:
    """
    Validate audio file structure (WK6 flat structure):
      assets/audio/sfx/<name>.wav (or .ogg)
      assets/audio/ambient/<name>.ogg (or .wav)

    WK6 Final: Flat contract keys (building_place, building_destroy, etc.).
    """
    findings: list[Finding] = []
    report: dict[str, Any] = {"category": "audio", "sfx": {}, "ambient": {}}

    # Validate SFX files (flat structure: sfx/<name>.wav or .ogg)
    sfx_dir = assets_root / "audio" / "sfx"
    if not sfx_dir.exists():
        findings.append(
            Finding(
                "error" if strict else "warn",
                "missing_audio_sfx_dir",
                "Missing audio SFX directory: assets/audio/sfx",
                str(sfx_dir),
            )
        )
        # Continue to check ambient even if SFX dir is missing
    else:
        if sfx_files:
            for sfx_name in sfx_files:
                # Check for .wav or .ogg (flat structure, no subdirectories)
                wav_path = sfx_dir / f"{sfx_name}.wav"
                ogg_path = sfx_dir / f"{sfx_name}.ogg"
                if wav_path.exists():
                    report["sfx"][sfx_name] = {"file": wav_path.name, "ok": True}
                elif ogg_path.exists():
                    report["sfx"][sfx_name] = {"file": ogg_path.name, "ok": True}
                else:
                    report["sfx"][sfx_name] = {"file": None, "ok": False}
                    findings.append(
                        Finding(
                            "error" if strict else "warn",
                            "missing_audio_sfx",
                            f"Missing audio SFX file: {sfx_name}.wav or {sfx_name}.ogg",
                            str(sfx_dir),
                        )
                    )

    # Validate ambient files
    ambient_dir = assets_root / "audio" / "ambient"
    if not ambient_dir.exists():
        findings.append(
            Finding(
                "error" if strict else "warn",
                "missing_audio_ambient_dir",
                "Missing audio ambient directory: assets/audio/ambient",
                str(ambient_dir),
            )
        )
    else:
        for ambient_name in ambient_files:
            # Check for .ogg or .wav
            ogg_path = ambient_dir / f"{ambient_name}.ogg"
            wav_path = ambient_dir / f"{ambient_name}.wav"
            if ogg_path.exists():
                report["ambient"][ambient_name] = {"file": ogg_path.name, "ok": True}
            elif wav_path.exists():
                report["ambient"][ambient_name] = {"file": wav_path.name, "ok": True}
            else:
                report["ambient"][ambient_name] = {"file": None, "ok": False}
                findings.append(
                    Finding(
                        "error" if strict else "warn",
                        "missing_audio_ambient",
                        f"Missing audio ambient file: {ambient_name}.ogg or {ambient_name}.wav",
                        str(ambient_dir),
                    )
                )

    return findings, report


def _resolve_prefab_model_path(models_root: Path, rel: str) -> tuple[Path | None, str | None]:
    """
    Resolve a prefab piece model path relative to assets/models/.
    Returns (absolute_path, error_reason) — error_reason set if invalid or not under models_root.
    """
    if not isinstance(rel, str) or not rel.strip():
        return None, "empty_or_non_string_model"
    norm = rel.replace("\\", "/").strip()
    if not norm or norm.startswith("/") or ".." in Path(norm).parts:
        return None, "invalid_model_path"
    candidate = (models_root / norm).resolve()
    try:
        candidate.relative_to(models_root.resolve())
    except ValueError:
        return None, "model_escapes_models_root"
    return candidate, None


def _resolve_prefab_asset_path(assets_root: Path, rel: str) -> tuple[Path | None, str | None]:
    """Resolve optional prefab asset paths, such as texture overrides, under assets/."""
    if not isinstance(rel, str) or not rel.strip():
        return None, "empty"
    norm = rel.replace("\\", "/").lstrip("/")
    if norm.startswith("assets/"):
        norm = norm[len("assets/") :]
    candidate = (assets_root / norm).resolve()
    assets_resolved = assets_root.resolve()
    try:
        candidate.relative_to(assets_resolved)
    except ValueError:
        return None, "escapes_assets_root"
    return candidate, None


def _validate_prefab_buildings(
    *,
    assets_root: Path,
    manifest: dict[str, Any],
) -> tuple[list[Finding], dict[str, Any]]:
    """
    Validate assets/prefabs/buildings/<prefab_id>.json per WK30 (manifest prefabs.buildings).
    Missing optional prefab → warn; missing required or malformed → error.
    """
    findings: list[Finding] = []
    report: dict[str, Any] = {"prefabs": {}}

    prefabs = manifest.get("prefabs") or {}
    buildings = prefabs.get("buildings") if isinstance(prefabs, dict) else None
    if not isinstance(buildings, dict):
        return findings, report

    required = buildings.get("required") or []
    optional = buildings.get("optional") or []
    if not isinstance(required, list):
        required = []
    if not isinstance(optional, list):
        optional = []

    prefab_dir = assets_root / "prefabs" / "buildings"
    models_root = (assets_root / "models").resolve()

    def check_one(prefab_id: str, *, is_required: bool) -> None:
        path = prefab_dir / f"{prefab_id}.json"
        entry: dict[str, Any] = {"path": str(path), "ok": False}
        start_idx = len(findings)

        if not path.is_file():
            msg = f"Missing prefab JSON: {prefab_id} (expected {path})"
            if is_required:
                findings.append(Finding("error", "missing_prefab_json", msg, str(path)))
            else:
                findings.append(Finding("warn", "missing_optional_prefab_json", msg, str(path)))
            entry["ok"] = not any(f.severity == "error" for f in findings[start_idx:])
            report["prefabs"][prefab_id] = entry
            return

        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            findings.append(Finding("error", "prefab_json_invalid", f"{prefab_id}: {e}", str(path)))
            entry["ok"] = not any(f.severity == "error" for f in findings[start_idx:])
            report["prefabs"][prefab_id] = entry
            return
        except OSError as e:
            findings.append(Finding("error", "prefab_json_read_error", f"{prefab_id}: {e}", str(path)))
            entry["ok"] = not any(f.severity == "error" for f in findings[start_idx:])
            report["prefabs"][prefab_id] = entry
            return

        if not isinstance(data, dict):
            findings.append(Finding("error", "prefab_json_not_object", f"{prefab_id}: root must be an object", str(path)))
            entry["ok"] = not any(f.severity == "error" for f in findings[start_idx:])
            report["prefabs"][prefab_id] = entry
            return

        missing_keys = PREFAB_BUILDING_REQUIRED_KEYS - set(data.keys())
        if missing_keys:
            findings.append(
                Finding(
                    "error",
                    "prefab_missing_keys",
                    f"{prefab_id}: missing keys: {sorted(missing_keys)}",
                    str(path),
                )
            )

        pid = data.get("prefab_id")
        if isinstance(pid, str) and pid != prefab_id:
            findings.append(
                Finding(
                    "warn",
                    "prefab_id_filename_mismatch",
                    f"{prefab_id}: prefab_id field {pid!r} does not match filename stem",
                    str(path),
                )
            )

        attr = data.get("attribution")
        if not isinstance(attr, list) or len(attr) == 0:
            findings.append(
                Finding("error", "prefab_attribution_empty", f"{prefab_id}: attribution must be a non-empty array", str(path))
            )
        elif not all(isinstance(x, str) and x.strip() for x in attr):
            findings.append(
                Finding(
                    "error",
                    "prefab_attribution_invalid",
                    f"{prefab_id}: attribution entries must be non-empty strings",
                    str(path),
                )
            )

        ft = data.get("footprint_tiles")
        if not isinstance(ft, list) or len(ft) != 2 or not all(isinstance(x, (int, float)) for x in ft):
            findings.append(
                Finding(
                    "error",
                    "prefab_footprint_invalid",
                    f"{prefab_id}: footprint_tiles must be [w, d] with two numbers",
                    str(path),
                )
            )

        pieces = data.get("pieces")
        if not isinstance(pieces, list):
            findings.append(Finding("error", "prefab_pieces_invalid", f"{prefab_id}: pieces must be an array", str(path)))
        else:
            if len(pieces) == 0:
                findings.append(Finding("warn", "prefab_pieces_empty", f"{prefab_id}: pieces array is empty", str(path)))
            for i, piece in enumerate(pieces):
                if not isinstance(piece, dict):
                    findings.append(
                        Finding("error", "prefab_piece_not_object", f"{prefab_id}: pieces[{i}] must be an object", str(path))
                    )
                    continue
                pk = PREFAB_PIECE_REQUIRED_KEYS - set(piece.keys())
                if pk:
                    findings.append(
                        Finding(
                            "error",
                            "prefab_piece_missing_keys",
                            f"{prefab_id}: pieces[{i}] missing keys: {sorted(pk)}",
                            str(path),
                        )
                    )
                rel = piece.get("model")
                resolved, _err = _resolve_prefab_model_path(models_root, rel if isinstance(rel, str) else "")
                if resolved is None:
                    findings.append(
                        Finding(
                            "error",
                            "prefab_piece_model_invalid",
                            f"{prefab_id}: pieces[{i}] model path invalid or escapes assets/models: {rel!r}",
                            str(path),
                        )
                    )
                elif not resolved.is_file():
                    findings.append(
                        Finding(
                            "error",
                            "prefab_piece_model_missing",
                            f"{prefab_id}: pieces[{i}] model file not found: {resolved}",
                            str(path),
                        )
                    )
                tex_override = piece.get("texture_override")
                if tex_override is not None:
                    tex_resolved, _tex_err = _resolve_prefab_asset_path(assets_root, tex_override if isinstance(tex_override, str) else "")
                    if tex_resolved is None:
                        findings.append(
                            Finding(
                                "error",
                                "prefab_piece_texture_override_invalid",
                                f"{prefab_id}: pieces[{i}] texture_override path invalid or escapes assets/: {tex_override!r}",
                                str(path),
                            )
                        )
                    elif not tex_resolved.is_file():
                        findings.append(
                            Finding(
                                "error",
                                "prefab_piece_texture_override_missing",
                                f"{prefab_id}: pieces[{i}] texture_override file not found: {tex_resolved}",
                                str(path),
                            )
                        )

        entry["ok"] = not any(f.severity == "error" for f in findings[start_idx:])
        report["prefabs"][prefab_id] = entry

    for pid in required:
        if isinstance(pid, str) and pid:
            check_one(pid, is_required=True)

    for pid in optional:
        if isinstance(pid, str) and pid:
            check_one(pid, is_required=False)

    return findings, report


def _validate_attribution(*, assets_root: Path, strict: bool) -> list[Finding]:
    findings: list[Finding] = []
    third_party = assets_root / "third_party"
    if not third_party.exists():
        # No third-party packs present -> no-op.
        return findings

    if not third_party.is_dir():
        return [Finding("error", "third_party_not_dir", "assets/third_party exists but is not a directory", str(third_party))]

    packs = sorted([p for p in third_party.iterdir() if p.is_dir()], key=lambda p: p.name.lower())

    # If packs exist, require verbatim LICENSE*/README* files within each pack dir.
    for pack in packs:
        has_license = False
        has_readme = False
        for f in pack.iterdir():
            if not f.is_file():
                continue
            n = f.name.lower()
            if n.startswith("license") and n.endswith(".txt"):
                has_license = True
            if n.startswith("readme") and n.endswith(".txt"):
                has_readme = True
        if not has_license:
            findings.append(Finding("error", "missing_pack_license", f"Missing LICENSE*.txt in third-party pack dir: {pack.name}", str(pack)))
        if not has_readme:
            findings.append(
                Finding(
                    "error" if strict else "warn",
                    "missing_pack_readme",
                    f"Missing README*.txt in third-party pack dir: {pack.name}",
                    str(pack),
                )
            )

    # If we have any third-party packs, require ATTRIBUTION.md in strict mode.
    attribution = assets_root / "ATTRIBUTION.md"
    if not attribution.exists():
        findings.append(
            Finding(
                "error" if (strict and len(packs) > 0) else "warn",
                "missing_attribution_rollup",
                "Missing assets/ATTRIBUTION.md rollup file",
                str(attribution),
            )
        )
    elif strict and len(packs) > 0:
        # Minimal "fully populated" check: the rollup must be non-empty and mention each pack dir name.
        try:
            txt = attribution.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            findings.append(Finding("error", "attribution_read_error", f"Failed to read assets/ATTRIBUTION.md: {e}", str(attribution)))
            txt = ""

        if not txt.strip():
            findings.append(Finding("error", "attribution_empty", "assets/ATTRIBUTION.md is empty", str(attribution)))
        else:
            lower = txt.lower()
            for pack in packs:
                if pack.name.lower() not in lower:
                    findings.append(
                        Finding(
                            "error",
                            "attribution_missing_pack_entry",
                            f"assets/ATTRIBUTION.md does not mention pack directory name: {pack.name}",
                            str(attribution),
                        )
                    )

    return findings


def _print_findings(findings: list[Finding]) -> None:
    if not findings:
        print("[validate_assets] OK: no findings")
        return
    for f in findings:
        loc = f" ({f.path})" if f.path else ""
        print(f"[validate_assets] {f.severity.upper()} {f.code}: {f.message}{loc}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate 3D model paths + audio + attribution (fast, no decoding).")
    ap.add_argument("--manifest", type=str, default=str(DEFAULT_MANIFEST), help="path to assets manifest JSON")
    ap.add_argument("--assets-root", type=str, default=str(DEFAULT_ASSETS_ROOT), help="assets root directory")
    ap.add_argument("--report", action="store_true", help="print human-readable report (default behavior)")
    ap.add_argument("--json", action="store_true", help="emit JSON report to stdout (for CI parsing)")
    ap.add_argument("--strict", action="store_true", help="non-zero exit if missing required folders/states")
    ap.add_argument("--check-attribution", action="store_true", help="validate assets/third_party/* license/readme scaffolding")
    ns = ap.parse_args()

    manifest_path = Path(ns.manifest)
    assets_root = Path(ns.assets_root)

    # Default to report mode if no explicit mode flags are set.
    if not (ns.report or ns.json or ns.strict or ns.check_attribution):
        ns.report = True

    try:
        manifest = _load_manifest(manifest_path)
    except Exception as e:
        print(f"[validate_assets] ERROR: failed to read manifest: {e} ({manifest_path})")
        return 2

    findings: list[Finding] = []
    full_report: dict[str, Any] = {"manifest": str(manifest_path), "assets_root": str(assets_root), "categories": {}}

    heroes = manifest.get("heroes", {})
    enemies = manifest.get("enemies", {})
    buildings = manifest.get("buildings", {})
    workers = manifest.get("workers", {})
    environment = manifest.get("environment", {})

    h_findings, h_report = _validate_model_tree(
        assets_root=assets_root,
        category="heroes",
        kinds=heroes.get("classes", []),
        strict=bool(ns.strict),
    )
    findings.extend(h_findings)
    full_report["categories"]["heroes"] = h_report

    e_findings, e_report = _validate_model_tree(
        assets_root=assets_root,
        category="enemies",
        kinds=enemies.get("types", []),
        strict=bool(ns.strict),
    )
    findings.extend(e_findings)
    full_report["categories"]["enemies"] = e_report

    b_findings, b_report = _validate_model_tree(
        assets_root=assets_root,
        category="buildings",
        kinds=buildings.get("types", []),
        strict=bool(ns.strict),
    )
    findings.extend(b_findings)
    full_report["categories"]["buildings"] = b_report

    w_findings, w_report = _validate_model_tree(
        assets_root=assets_root,
        category="workers",
        kinds=workers.get("types", []),
        strict=bool(ns.strict),
    )
    findings.extend(w_findings)
    full_report["categories"]["workers"] = w_report

    env_findings, env_report = _validate_model_tree(
        assets_root=assets_root,
        category="environment",
        kinds=environment.get("types", []),
        strict=bool(ns.strict),
    )
    findings.extend(env_findings)
    full_report["categories"]["environment"] = env_report

    textures = manifest.get("textures") or {}
    tex_rels: list[str] = []
    if isinstance(textures, dict):
        raw = textures.get("files")
        if isinstance(raw, list):
            tex_rels = [x for x in raw if isinstance(x, str)]
    if tex_rels:
        t_findings, t_report = _validate_texture_files(assets_root=assets_root, rel_paths=tex_rels)
        findings.extend(t_findings)
        full_report["categories"]["textures"] = t_report

    # Validate audio assets (WK6)
    audio = manifest.get("audio", {})
    if audio:
        a_findings, a_report = _validate_audio_tree(
            assets_root=assets_root,
            sfx_files=audio.get("sfx", []),
            ambient_files=audio.get("ambient", []),
            strict=bool(ns.strict),
        )
        findings.extend(a_findings)
        full_report["categories"]["audio"] = a_report

    p_findings, p_report = _validate_prefab_buildings(assets_root=assets_root, manifest=manifest)
    findings.extend(p_findings)
    full_report["categories"]["prefabs"] = p_report

    if ns.check_attribution:
        findings.extend(_validate_attribution(assets_root=assets_root, strict=bool(ns.strict)))

    # Output
    if ns.json:
        # Keep it single JSON object for easy tooling.
        serial = {
            "report": full_report,
            "findings": [f.__dict__ for f in findings],
        }
        print(json.dumps(serial, ensure_ascii=False))
    else:
        if ns.report:
            _print_findings(findings)
            # Compact summary for quick scan.
            errors = len([f for f in findings if f.severity == "error"])
            warns = len([f for f in findings if f.severity == "warn"])
            print(f"[validate_assets] SUMMARY errors={errors} warns={warns}")

    # Any error-level finding fails the run (report + strict). Warnings never fail.
    if any(f.severity == "error" for f in findings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
