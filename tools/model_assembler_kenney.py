"""
Kenney Kit Assembler (tools/model_assembler_kenney.py) - v0.1 (WK28 spike).

Interactive Ursina-based kitbash tool. Lets a human assemble Kenney ``.glb`` kit
pieces into saved **building prefab JSON** files under
``assets/prefabs/buildings/``. Downstream consumers (future in-game renderer,
other tools) read the same schema documented in ``assets/prefabs/schema.md``.

Key design decisions (see ``.cursor/plans/wk28_assembler_spike_41c2daeb.plan.md``):
- Reuses the piece scan pattern and the **two-path shader classifier**
  (``_apply_gltf_color_and_shading``) from ``tools/model_viewer_kenney.py`` so
  textured pieces (Retro Fantasy / Survival) stay on the default unlit shader,
  while factor-only pieces (Nature Kit) get the custom ``factor_lit_shader``
  (not flat white, not pitch black). See
  ``.cursor/plans/kenney_gltf_ursina_integration_guide.md`` Section 5.
- Saves + loads plain JSON matching ``assets/prefabs/schema.md``; no baking,
  no ``.glb`` export (deferred past v0.1).
- Does NOT modify anything under ``game/``, ``ai/``, or ``config.py``.

**WK31:** Display scale applies ``tools/kenney_pack_scale.pack_extent_multiplier_for_rel``
per model path on top of authored JSON ``scale`` (Retro = 1.0); saved JSON stays logical.

Usage (from repo root):
    python tools/model_assembler_kenney.py --new
    python tools/model_assembler_kenney.py --open peasant_house_small_v1
    python tools/model_assembler_kenney.py --new --prefab-id my_house_v1

Controls (hover the 3D scene; UI clicks route to UI, not the scene):
    Left-click ground       - place currently selected library piece (1-unit grid snap)
    Left-click placed piece - select that piece
    WASD                    - nudge selected piece by 1.0 units on XZ
    Shift+WASD              - nudge selected piece by 0.25 units on XZ (fine; flush kitbash)
    Q / E                   - rotate selected piece 90 deg around Y
    [ / ]                   - move selected piece Y by 0.25 units
    Shift+[ / Shift+]       - move selected piece Y by 0.05 units (fine vertical)
    -  (numpad subtract)    - uniform shrink selected piece (logical scale × ~0.98)
    =                        - uniform grow selected piece (logical scale × ~1.02)
    Shift + - / =           - finer nudge (× ~0.995 / ~1.005; same as Shift+WASD pattern)
    Delete / Backspace      - remove selected piece
    Right-drag / MMB drag   - orbit / pan camera (EditorCamera)
    Scroll wheel            - zoom
    ESC                     - close modal / open-prefab dialog only (does not exit)
    Ctrl+Q                  - quit the assembler
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Only .glb/.gltf pieces; OBJ/FBX/DAE are duplicate Kenney exports we avoid.
MODEL_EXTS = {".glb", ".gltf"}

# Folders scanned for the left-side piece library.
#
# Merged trees:
#   ``Models/GLB format``  -> Retro Fantasy (named textures) + Survival (shared
#   ``colormap.png``) + Blocky Characters (``texture-a.png`` ... ``texture-r.png``)
#   + Fantasy Town (``*-fantasy-town.glb`` + ``Textures/colormap-fantasy-town.png``)
#   + Graveyard (``*-graveyard.glb`` + ``Textures/colormap-graveyard.png``). Since
#   WK31 round-2 every Fantasy Town / Graveyard file carries a pack suffix and
#   references a pack-suffixed colormap, so the merged tree is collision-free
#   and each piece's textures resolve correctly.
#   ``Models/GLTF format`` -> Nature Kit (factor-only; needs custom lit shader)
#
# See ``kenney_assets_models_mapping.plan.md`` §3 and §4 for the rename design.
PIECE_LIB_SUBDIRS: tuple[str, ...] = (
    "Models/GLB format",
    "Models/GLTF format",
)

# Filename-suffix -> Kenney pack id for attribution inference on merged pieces.
FILENAME_SUFFIX_PACK_IDS: dict[str, str] = {
    "-fantasy-town": "kenney_fantasy-town-kit_2.0",
    "-graveyard": "kenney_graveyard-kit_5.0",
}

# Raw-tree pack folder -> Kenney pack id (for prefab JSON ``attribution``) when
# a human explicitly authors a prefab with a raw-tree ``Models/Kenny raw
# downloads.../<pack>/...`` model path (uncommon after the WK31 rename).
RAW_TREE_PACK_IDS: dict[str, str] = {
    "kenney_fantasy-town-kit_2.0": "kenney_fantasy-town-kit_2.0",
    "kenney_graveyard-kit_5.0": "kenney_graveyard-kit_5.0",
    "kenney_retro-fantasy-kit": "kenney_retro-fantasy-kit",
    "kenney_survival-kit": "kenney_survival-kit",
    "kenney_nature-kit": "kenney_nature-kit",
    "kenney_blocky-characters_20": "kenney_blocky-characters_20",
}

ASSETS_MODELS = PROJECT_ROOT / "assets" / "models"
DEFAULT_OUT_DIR = PROJECT_ROOT / "assets" / "prefabs" / "buildings"

GRID_HALF = 5  # ground grid extends +/-5 cells on X and Z (10x10 cells total)
GRID_CELL = 1.0
NUDGE_STEP = 1.0
NUDGE_FINE_STEP = 0.25  # Shift+WASD; matches Y_STEP for consistent sub-grid placement
ROT_STEP = 90.0
Y_STEP = 0.25
Y_STEP_FINE = 0.05  # Shift+[ / Shift+]

# Uniform multiplicative nudge for logical `scale` (JSON); on-Entity display uses
# `piece.scale * pack_extent_multiplier_for_rel` — never bake the pack factor into JSON.
SCALE_NUDGE_FACTOR = 1.02
SCALE_NUDGE_FACTOR_FINE = 1.005
SCALE_LOGICAL_MIN = 0.01
SCALE_LOGICAL_MAX = 5.0

DEFAULT_PREFAB_ID = "untitled_v1"
DEFAULT_BUILDING_TYPE = "house"
DEFAULT_FOOTPRINT = [1, 1]
DEFAULT_ROTATION_STEPS = 90
DEFAULT_GROUND_Y = 0.0


# -- Reuse helpers from the viewer (same Agent 12 ownership) -------------------
# We import the private helpers deliberately: both tools are owned by
# Agent 12 (ToolsDevEx_Lead) and the shader classifier is the canonical piece
# of logic we want to keep in lockstep between viewer and assembler.
sys.path.insert(0, str(PROJECT_ROOT))
from tools.kenney_pack_scale import (  # noqa: E402
    apply_kenney_pack_color_tint_to_entity,
    pack_extent_multiplier_for_rel,
)
from tools.model_viewer_kenney import (  # noqa: E402
    _apply_gltf_color_and_shading,
    _load_model_node_from_file,
    _setup_scene_lighting,
)
from game.graphics.prefab_texture_overrides import apply_prefab_texture_override  # noqa: E402


# -- Data -----------------------------------------------------------------------


@dataclass
class PlacedPiece:
    """A piece placed in the scene. Mirrors one item in the saved prefab JSON."""

    model_rel: str  # POSIX path relative to assets/models/ (goes in JSON)
    entity: Any = None  # ursina.Entity instance
    pos: tuple[float, float, float] = (0.0, 0.0, 0.0)
    rot_y: float = 0.0  # Y rotation in degrees (Euler; only Y used by tool)
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0)
    texture_override: str | None = None
    texture_override_mode: str | None = None

    def to_json(self) -> dict:
        out = {
            "model": self.model_rel,
            "pos": [float(self.pos[0]), float(self.pos[1]), float(self.pos[2])],
            "rot": [0.0, float(self.rot_y), 0.0],
            "scale": [float(self.scale[0]), float(self.scale[1]), float(self.scale[2])],
        }
        if self.texture_override:
            out["texture_override"] = self.texture_override
        if self.texture_override_mode:
            out["texture_override_mode"] = self.texture_override_mode
        return out


@dataclass
class PrefabState:
    prefab_id: str = DEFAULT_PREFAB_ID
    building_type: str = DEFAULT_BUILDING_TYPE
    footprint_tiles: list[int] = field(default_factory=lambda: list(DEFAULT_FOOTPRINT))
    ground_anchor_y: float = DEFAULT_GROUND_Y
    rotation_steps: int = DEFAULT_ROTATION_STEPS
    attribution: list[str] = field(default_factory=list)
    notes: str = ""


# -- Library scan ---------------------------------------------------------------


def _pack_id_for_filename_suffix(name: str) -> str | None:
    """Return the Kenney pack id for a filename that carries a pack suffix.

    E.g. ``cart-fantasy-town.glb`` -> ``kenney_fantasy-town-kit_2.0``.
    Returns ``None`` for filenames that don't carry any known suffix.
    """
    stem = Path(name).stem
    for sfx, pack_id in FILENAME_SUFFIX_PACK_IDS.items():
        if stem.endswith(sfx):
            return pack_id
    return None


def _collect_piece_library(assets_models: Path) -> list[tuple[str, str]]:
    """Return a sorted list of (display_name, rel_path_posix) for selectable pieces.

    rel_path_posix is relative to ``assets/models/`` (POSIX slashes) so it goes
    directly into the saved JSON ``model`` field.

    Display names are the plain filename (the WK31 rename embedded the pack id
    into the filename itself for Fantasy Town / Graveyard, e.g.
    ``cart-fantasy-town.glb``, so no extra UI tag is needed).
    """
    out: list[tuple[str, str]] = []
    seen_rel: set[str] = set()
    for sub in PIECE_LIB_SUBDIRS:
        sub_dir = assets_models / sub
        if not sub_dir.is_dir():
            continue
        for p in sorted(sub_dir.rglob("*"), key=lambda x: str(x).lower()):
            if not p.is_file() or p.suffix.lower() not in MODEL_EXTS:
                continue
            try:
                rel = p.relative_to(assets_models).as_posix()
            except ValueError:
                continue
            if rel in seen_rel:
                continue
            seen_rel.add(rel)
            out.append((p.name, rel))
    return out


def _guess_attribution(pieces: list[PlacedPiece]) -> list[str]:
    """Infer a best-effort attribution list from the placed pieces' rel paths.

    Filename-suffixed pieces (``*-fantasy-town.glb`` / ``*-graveyard.glb``) are
    attributed via :data:`FILENAME_SUFFIX_PACK_IDS` — this covers every piece
    authored from the merged tree after the WK31 rename.

    Raw-tree pieces (``Models/Kenny raw downloads (for exact paths)/kenney_*/...``)
    attribute directly to their pack id via :data:`RAW_TREE_PACK_IDS`.

    Other merged-tree pieces fall back to the well-known per-folder pair:
    ``Models/GLB format`` -> Retro Fantasy + Survival (+ Blocky Characters if
    any ``character-<a..r>.glb`` is placed), ``Models/GLTF format`` -> Nature
    Kit. The human should trim via the "Attrib" UI before committing a real
    prefab.
    """
    out: set[str] = set()
    for piece in pieces:
        rel = piece.model_rel
        filename = Path(rel).name

        pack_from_suffix = _pack_id_for_filename_suffix(filename)
        if pack_from_suffix is not None:
            out.add(pack_from_suffix)
            continue

        parts = Path(rel).parts
        matched = False
        for seg in parts:
            if seg in RAW_TREE_PACK_IDS:
                out.add(RAW_TREE_PACK_IDS[seg])
                matched = True
                break
        if matched:
            continue

        head = "/".join(parts[:2])
        if head == "Models/GLB format":
            stem = Path(filename).stem
            if stem.startswith("character-") and len(stem) == len("character-x"):
                out.add("kenney_blocky-characters_20")
            else:
                out.add("kenney_retro-fantasy-kit")
                out.add("kenney_survival-kit")
        elif head == "Models/GLTF format":
            out.add("kenney_nature-kit")
    return sorted(out)


# -- Prefab JSON IO -------------------------------------------------------------


def _load_prefab_json(out_dir: Path, prefab_id: str) -> dict | None:
    f = out_dir / f"{prefab_id}.json"
    if not f.is_file():
        return None
    with f.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _save_prefab_json(
    out_dir: Path,
    meta: PrefabState,
    pieces: list[PlacedPiece],
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    attribution = meta.attribution or _guess_attribution(pieces)
    payload = {
        "prefab_id": meta.prefab_id,
        "building_type": meta.building_type,
        "footprint_tiles": [int(meta.footprint_tiles[0]), int(meta.footprint_tiles[1])],
        "ground_anchor_y": float(meta.ground_anchor_y),
        "rotation_steps": int(meta.rotation_steps),
        "attribution": list(attribution),
        "pieces": [p.to_json() for p in pieces],
        "notes": meta.notes or "",
    }
    out_path = out_dir / f"{meta.prefab_id}.json"
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
        fh.write("\n")
    return out_path


# -- Snap / geometry ------------------------------------------------------------


def _snap(v: float, step: float = GRID_CELL) -> float:
    """Snap ``v`` to the nearest multiple of ``step`` centered at step*0.5.

    Placement sits at cell centers: for step=1.0, valid values are
    ..., -1.5, -0.5, 0.5, 1.5, ...
    """
    # shift so cell centers land on multiples of step
    return round((v - step * 0.5) / step) * step + step * 0.5


# -- Assembler app --------------------------------------------------------------


class AssemblerApp:
    def __init__(
        self,
        *,
        assets_models: Path,
        out_dir: Path,
        prefab_id: str,
        open_existing: bool,
        auto_exit_sec: float = 0.0,
        screenshot_subdir: str | None = None,
        screenshot_stem: str | None = None,
    ) -> None:
        self.assets_models = assets_models
        self.out_dir = out_dir
        self.meta = PrefabState(prefab_id=prefab_id)
        self.auto_exit_sec = float(auto_exit_sec or 0.0)
        self.screenshot_subdir = screenshot_subdir
        self.screenshot_stem = screenshot_stem

        self.library: list[tuple[str, str]] = _collect_piece_library(assets_models)
        self.library_filtered: list[tuple[str, str]] = list(self.library)
        self.list_start = 0
        self.list_page_size = 16

        self.pieces: list[PlacedPiece] = []
        self.selected: PlacedPiece | None = None
        self.current_piece_rel: str | None = None

        # Ursina entities and UI handles (populated by build_*)
        self.ground_entity: Any = None
        self.selection_marker: Any = None
        self.list_buttons: list[Any] = []
        self.status_text: Any = None
        self.toast_text: Any = None
        self.filter_field: Any = None
        self.current_library_label: Any = None
        self.current_meta_label: Any = None
        self.modal_field: Any = None
        self.modal_ok: Any = None
        self.modal_cancel: Any = None
        self.modal_title: Any = None
        self.open_dialog_entities: list[Any] = []

        self._toast_until_ms = 0
        self._app: Any = None

        if open_existing:
            self._load_from_disk(prefab_id)

    # ------------------------------------------------------------------
    # Prefab IO
    # ------------------------------------------------------------------
    def _load_from_disk(self, prefab_id: str) -> None:
        data = _load_prefab_json(self.out_dir, prefab_id)
        if data is None:
            print(
                f"[assembler] --open {prefab_id}: not found under {self.out_dir}; "
                "starting fresh with that id."
            )
            return
        self.meta = PrefabState(
            prefab_id=str(data.get("prefab_id", prefab_id)),
            building_type=str(data.get("building_type", DEFAULT_BUILDING_TYPE)),
            footprint_tiles=list(data.get("footprint_tiles", DEFAULT_FOOTPRINT))[:2] or list(DEFAULT_FOOTPRINT),
            ground_anchor_y=float(data.get("ground_anchor_y", DEFAULT_GROUND_Y)),
            rotation_steps=int(data.get("rotation_steps", DEFAULT_ROTATION_STEPS)),
            attribution=list(data.get("attribution") or []),
            notes=str(data.get("notes") or ""),
        )
        # Defer piece instantiation until Ursina scene is ready; stash the raw data.
        self._pending_pieces = list(data.get("pieces") or [])

    def _instantiate_pending_pieces(self) -> None:
        for raw in getattr(self, "_pending_pieces", []):
            rel = str(raw.get("model") or "").replace("\\", "/")
            if not rel:
                continue
            pos = raw.get("pos", [0.0, 0.0, 0.0])
            rot = raw.get("rot", [0.0, 0.0, 0.0])
            scl = raw.get("scale", [1.0, 1.0, 1.0])
            pos_t = (float(pos[0]), float(pos[1]), float(pos[2]))
            rot_y = float(rot[1]) if len(rot) > 1 else 0.0
            scl_t = (float(scl[0]), float(scl[1]), float(scl[2]))
            self._spawn_piece_core(
                rel=rel,
                pos=pos_t,
                rot_y=rot_y,
                scale=scl_t,
                texture_override=raw.get("texture_override"),
                texture_override_mode=raw.get("texture_override_mode"),
                select=False,
            )
        self._pending_pieces = []

    # ------------------------------------------------------------------
    # Scene build
    # ------------------------------------------------------------------
    def build(self) -> Any:
        from ursina import (
            Entity,
            Text,
            Ursina,
            Vec3,
            application,
            camera,
            color,
            scene,
            window,
            EditorCamera,
        )
        from ursina.shaders import unlit_shader
        from panda3d.core import LVecBase4f, getModelPath

        os.chdir(PROJECT_ROOT)

        self._app = Ursina(
            title=f"Kingdom Sim - Kenney Kit Assembler ({self.meta.prefab_id})",
            borderless=False,
            fullscreen=False,
            development_mode=False,
        )

        application.asset_folder = Path(PROJECT_ROOT)
        getModelPath().append_directory(str(PROJECT_ROOT.resolve()))

        window.exit_button.visible = False
        window.fps_counter.enabled = True
        try:
            scene.clearFog()
            self._app.setBackgroundColor(LVecBase4f(0.12, 0.13, 0.15, 1))
        except Exception:
            pass

        # Ground slab (invisible collider) so mouse picking returns world_point.
        self.ground_entity = Entity(
            parent=scene,
            model="cube",
            scale=(GRID_HALF * 2 + 4, 0.05, GRID_HALF * 2 + 4),
            position=(0.0, -0.025, 0.0),
            collider="box",
            color=color.rgba(0.18, 0.20, 0.22, 1.0),
            shader=unlit_shader,
        )
        self.ground_entity.assembler_role = "ground"

        # Visible 1x1 grid lines on XZ plane.
        try:
            from ursina.models.procedural import Grid
            Entity(
                parent=scene,
                model=Grid(GRID_HALF * 2, GRID_HALF * 2),
                rotation=(90, 0, 0),
                position=(0, 0.001, 0),
                scale=(GRID_HALF * 2.0, 1, GRID_HALF * 2.0),
                color=color.rgba(0.45, 0.48, 0.55, 1.0),
                collision=False,
                shader=unlit_shader,
            )
        except Exception:
            pass

        # Origin marker (small cyan cube at prefab origin).
        Entity(
            parent=scene,
            model="cube",
            scale=(0.14, 0.14, 0.14),
            position=(0, 0.08, 0),
            color=color.cyan,
            collision=False,
            shader=unlit_shader,
        )

        # Axis helpers (X=red, Z=blue) for orientation legibility.
        Entity(
            parent=scene,
            model="cube",
            scale=(GRID_HALF * 2.0, 0.02, 0.02),
            position=(0, 0.006, 0),
            color=color.rgba(0.85, 0.30, 0.30, 1.0),
            collision=False,
            shader=unlit_shader,
        )
        Entity(
            parent=scene,
            model="cube",
            scale=(0.02, 0.02, GRID_HALF * 2.0),
            position=(0, 0.006, 0),
            color=color.rgba(0.30, 0.55, 0.95, 1.0),
            collision=False,
            shader=unlit_shader,
        )

        _setup_scene_lighting(center_x=0.0, center_z=0.0, span=float(GRID_HALF * 4))

        self._build_ui()

        # Instantiate any pieces loaded from disk (after scene+lighting is ready).
        self._instantiate_pending_pieces()

        camera.fov = 50
        camera.clip_plane_near = 0.05
        camera.clip_plane_far = 5000.0
        if self.auto_exit_sec > 0.0:
            camera.position = Vec3(0, 8, -12)
            camera.look_at(Vec3(0, 0.8, 0))
        else:
            # Camera: EditorCamera centered on origin, elevated back view.
            ec = EditorCamera()
            ec.position = Vec3(0, 0, 0)
            camera.position = Vec3(0, 8, -12)
            ec.rotation = Vec3(35.0, 0.0, 0.0)
            try:
                camera.editor_position = camera.position
            except Exception:
                pass
            ec.target_z = camera.z

        self._install_input_hook()
        self._refresh_status()
        if self.auto_exit_sec > 0.0:
            from tools.ursina_capture import install_auto_capture, resolve_tool_screenshot_path

            out_path = resolve_tool_screenshot_path(
                subdir=self.screenshot_subdir,
                stem=self.screenshot_stem or f"assembler_{self.meta.prefab_id}",
            )
            install_auto_capture(app=self._app, seconds=self.auto_exit_sec, out_path=out_path)
        return self._app

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        from ursina import Button, Entity, Text, camera, color
        from ursina.prefabs.input_field import InputField

        # Left-side library panel background (visual anchor only).
        Entity(
            parent=camera.ui,
            model="quad",
            color=color.rgba(0.08, 0.09, 0.11, 0.78),
            scale=(0.42, 0.92),
            position=(-0.58, 0.0, 0.1),
        )
        Text(
            text="Piece library",
            parent=camera.ui,
            position=(-0.78, 0.44),
            scale=1.1,
            color=color.azure,
        )

        # Filter InputField (top of library panel).
        self.filter_field = InputField(
            parent=camera.ui,
            default_value="",
            position=(-0.58, 0.40),
            scale=(0.38, 0.035),
            limit_content_to=None,
        )
        # InputField.on_value_changed fires every keystroke in recent Ursina.
        self.filter_field.on_value_changed = self._on_filter_changed

        # Up / Down page buttons.
        Button(
            text="prev",
            parent=camera.ui,
            position=(-0.74, 0.36),
            scale=(0.07, 0.03),
            color=color.rgba(0.25, 0.28, 0.35, 1.0),
            on_click=self._on_list_prev,
        )
        Button(
            text="next",
            parent=camera.ui,
            position=(-0.42, 0.36),
            scale=(0.07, 0.03),
            color=color.rgba(0.25, 0.28, 0.35, 1.0),
            on_click=self._on_list_next,
        )

        # Library row buttons (rebuilt on filter / page changes).
        # Ursina only creates Button.text_entity when initial text is non-empty,
        # so seed with a space placeholder and guard every text_entity access.
        self.list_buttons = []
        for i in range(self.list_page_size):
            y = 0.32 - i * 0.04
            btn = Button(
                text=" ",
                parent=camera.ui,
                position=(-0.58, y),
                scale=(0.38, 0.034),
                color=color.rgba(0.16, 0.18, 0.22, 1.0),
                text_color=color.white,
            )
            if getattr(btn, "text_entity", None) is not None:
                btn.text_entity.scale = 0.55
                btn.text_entity.origin = (-0.5, 0)
            btn.assembler_row = i
            btn.on_click = (lambda b=btn: self._on_list_row_clicked(b))
            self.list_buttons.append(btn)

        self.current_library_label = Text(
            text="selected piece: (none)",
            parent=camera.ui,
            position=(-0.78, -0.44),
            scale=0.8,
            color=color.light_gray,
        )
        self._refresh_list_buttons()

        # Toolbar across the top.
        bar_y = 0.47
        x0 = -0.40
        btn_w = 0.12
        btn_h = 0.04
        btn_gap = 0.01

        def _place_btn(ix: int, text: str, handler) -> Any:
            b = Button(
                text=text,
                parent=camera.ui,
                position=(x0 + ix * (btn_w + btn_gap), bar_y),
                scale=(btn_w, btn_h),
                color=color.rgba(0.22, 0.26, 0.34, 1.0),
            )
            b.on_click = handler
            return b

        _place_btn(0, "New",   self._on_new_pressed)
        _place_btn(1, "Open",  self._on_open_pressed)
        _place_btn(2, "Save",  self._on_save_pressed)
        _place_btn(3, "ID...", self._on_edit_prefab_id)
        _place_btn(4, "Type...", self._on_edit_building_type)
        _place_btn(5, "WxD...", self._on_edit_footprint)
        _place_btn(6, "Attrib...", self._on_edit_attribution)

        # Live meta label under the toolbar.
        self.current_meta_label = Text(
            text="",
            parent=camera.ui,
            position=(-0.40, 0.43),
            scale=0.75,
            color=color.light_gray,
        )

        # Status bar at the bottom.
        self.status_text = Text(
            text="",
            parent=camera.ui,
            position=(-0.40, -0.46),
            scale=0.8,
            color=color.white,
        )

        # Brief save / error toast.
        self.toast_text = Text(
            text="",
            parent=camera.ui,
            position=(0.0, 0.38),
            scale=1.0,
            color=color.lime,
            origin=(0, 0),
        )

        # Help text (bottom-right).
        Text(
            text=(
                "LMB=place/select  WASD=nudge1  Shift+WASD=nudge0.25  Q/E=rotate  "
                "[ / ]=y0.25  Shift+[ / ]=y0.05  Del=remove  RMB=orbit  MMB=pan  "
                "Scroll=zoom  ESC=dialogs  Ctrl+Q=quit"
            ),
            parent=camera.ui,
            position=(-0.40, -0.49),
            scale=0.6,
            color=color.rgba(0.75, 0.78, 0.82, 1.0),
        )

    # -- list / filter --------------------------------------------------
    def _on_filter_changed(self) -> None:
        q = (self.filter_field.text or "").strip().lower() if self.filter_field else ""
        if not q:
            self.library_filtered = list(self.library)
        else:
            self.library_filtered = [
                (name, rel) for (name, rel) in self.library
                if q in name.lower() or q in rel.lower()
            ]
        self.list_start = 0
        self._refresh_list_buttons()

    def _on_list_prev(self) -> None:
        self.list_start = max(0, self.list_start - self.list_page_size)
        self._refresh_list_buttons()

    def _on_list_next(self) -> None:
        if self.list_start + self.list_page_size < len(self.library_filtered):
            self.list_start += self.list_page_size
            self._refresh_list_buttons()

    def _on_list_row_clicked(self, btn: Any) -> None:
        idx = self.list_start + int(getattr(btn, "assembler_row", -1))
        if 0 <= idx < len(self.library_filtered):
            name, rel = self.library_filtered[idx]
            self.current_piece_rel = rel
            if self.current_library_label is not None:
                self.current_library_label.text = f"selected piece: {name}"
            self._refresh_list_buttons()

    def _refresh_list_buttons(self) -> None:
        from ursina import color
        total = len(self.library_filtered)
        for i, btn in enumerate(self.list_buttons):
            idx = self.list_start + i
            if idx < total:
                name, rel = self.library_filtered[idx]
                short = name if len(name) <= 36 else name[:33] + "..."
                btn.text = short
                btn.enabled = True
                is_cur = (rel == self.current_piece_rel)
                btn.color = color.rgba(0.38, 0.46, 0.60, 1.0) if is_cur else color.rgba(0.16, 0.18, 0.22, 1.0)
            else:
                btn.text = " "
                btn.enabled = False

    # -- toolbar handlers ----------------------------------------------
    def _on_new_pressed(self) -> None:
        for p in list(self.pieces):
            self._remove_piece(p)
        self.meta = PrefabState()
        self._close_modal()
        self._set_title()
        self._refresh_status()
        self._show_toast("new prefab")

    def _on_open_pressed(self) -> None:
        self._open_prefab_dialog()

    def _on_save_pressed(self) -> None:
        try:
            out = _save_prefab_json(self.out_dir, self.meta, self.pieces)
            try:
                rel = out.relative_to(PROJECT_ROOT)
            except ValueError:
                rel = out
            self._show_toast(f"saved: {rel}")
            self._refresh_status()
        except Exception as exc:
            self._show_toast(f"save failed: {exc!r}", err=True)

    def _on_edit_prefab_id(self) -> None:
        self._open_modal("prefab_id (filename stem)", self.meta.prefab_id, self._apply_prefab_id)

    def _on_edit_building_type(self) -> None:
        self._open_modal("building_type (matches config.py key)", self.meta.building_type, self._apply_building_type)

    def _on_edit_footprint(self) -> None:
        cur = f"{self.meta.footprint_tiles[0]}x{self.meta.footprint_tiles[1]}"
        self._open_modal("footprint WxD (tiles, e.g. 1x1)", cur, self._apply_footprint)

    def _on_edit_attribution(self) -> None:
        cur = ", ".join(self.meta.attribution)
        self._open_modal(
            "attribution (comma-separated pack ids)",
            cur,
            self._apply_attribution,
        )

    def _apply_prefab_id(self, value: str) -> None:
        val = value.strip()
        if not val:
            self._show_toast("prefab_id cannot be empty", err=True)
            return
        # POSIX-safe filename: allow letters, digits, _, -, dot.
        bad = [c for c in val if not (c.isalnum() or c in "_-.")]
        if bad:
            self._show_toast(f"invalid chars in prefab_id: {bad!r}", err=True)
            return
        self.meta.prefab_id = val
        self._close_modal()
        self._set_title()
        self._refresh_status()

    def _apply_building_type(self, value: str) -> None:
        val = value.strip() or DEFAULT_BUILDING_TYPE
        self.meta.building_type = val
        self._close_modal()
        self._refresh_status()

    def _apply_footprint(self, value: str) -> None:
        try:
            parts = value.lower().replace(" ", "").split("x")
            if len(parts) != 2:
                raise ValueError("want WxD, e.g. 1x1 or 2x3")
            w = int(parts[0])
            d = int(parts[1])
            if w <= 0 or d <= 0:
                raise ValueError("dimensions must be >= 1")
            self.meta.footprint_tiles = [w, d]
            self._close_modal()
            self._refresh_status()
        except Exception as exc:
            self._show_toast(f"bad footprint: {exc}", err=True)

    def _apply_attribution(self, value: str) -> None:
        items = [s.strip() for s in value.split(",")]
        self.meta.attribution = [s for s in items if s]
        self._close_modal()
        self._refresh_status()

    # -- modal input ---------------------------------------------------
    def _open_modal(self, title: str, initial: str, on_ok) -> None:
        self._close_modal()
        from ursina import Button, Text, camera, color
        from ursina.prefabs.input_field import InputField

        self.modal_title = Text(
            text=title,
            parent=camera.ui,
            position=(0.0, 0.12),
            scale=1.0,
            color=color.white,
            origin=(0, 0),
        )
        self.modal_field = InputField(
            parent=camera.ui,
            default_value=initial,
            position=(0.0, 0.06),
            scale=(0.5, 0.04),
        )
        self.modal_field.active = True

        self.modal_ok = Button(
            text="OK",
            parent=camera.ui,
            position=(-0.07, 0.00),
            scale=(0.08, 0.04),
            color=color.rgba(0.26, 0.50, 0.34, 1.0),
        )
        self.modal_ok.on_click = lambda: on_ok(self.modal_field.text)
        self.modal_cancel = Button(
            text="Cancel",
            parent=camera.ui,
            position=(0.07, 0.00),
            scale=(0.08, 0.04),
            color=color.rgba(0.40, 0.20, 0.20, 1.0),
        )
        self.modal_cancel.on_click = self._close_modal

    def _close_modal(self) -> None:
        for attr in ("modal_title", "modal_field", "modal_ok", "modal_cancel"):
            ent = getattr(self, attr, None)
            if ent is not None:
                try:
                    ent.enabled = False
                    from ursina import destroy
                    destroy(ent)
                except Exception:
                    pass
                setattr(self, attr, None)

    # -- open prefab picker --------------------------------------------
    def _open_prefab_dialog(self) -> None:
        self._close_modal()
        self._close_open_dialog()
        from ursina import Button, Entity, Text, camera, color
        files = sorted(self.out_dir.glob("*.json")) if self.out_dir.is_dir() else []
        bg = Entity(
            parent=camera.ui,
            model="quad",
            color=color.rgba(0.09, 0.10, 0.12, 0.95),
            scale=(0.5, 0.55),
            position=(0.0, 0.0, 0.05),
        )
        self.open_dialog_entities.append(bg)
        title = Text(
            text="Open prefab",
            parent=camera.ui,
            position=(0.0, 0.22),
            scale=1.1,
            color=color.azure,
            origin=(0, 0),
        )
        self.open_dialog_entities.append(title)

        if not files:
            note = Text(
                text=f"No prefabs in {self.out_dir}",
                parent=camera.ui,
                position=(0.0, 0.06),
                scale=0.85,
                color=color.light_gray,
                origin=(0, 0),
            )
            self.open_dialog_entities.append(note)

        row_h = 0.045
        max_rows = 8
        for i, f in enumerate(files[:max_rows]):
            y = 0.15 - i * row_h
            btn = Button(
                text=f.stem,
                parent=camera.ui,
                position=(0.0, y),
                scale=(0.44, row_h - 0.005),
                color=color.rgba(0.18, 0.22, 0.30, 1.0),
            )
            if getattr(btn, "text_entity", None) is not None:
                btn.text_entity.scale = 0.65
            btn.on_click = (lambda pid=f.stem: self._apply_open(pid))
            self.open_dialog_entities.append(btn)

        cancel = Button(
            text="Cancel",
            parent=camera.ui,
            position=(0.0, -0.22),
            scale=(0.12, 0.04),
            color=color.rgba(0.40, 0.20, 0.20, 1.0),
        )
        cancel.on_click = self._close_open_dialog
        self.open_dialog_entities.append(cancel)

    def _close_open_dialog(self) -> None:
        for ent in self.open_dialog_entities:
            try:
                ent.enabled = False
                from ursina import destroy
                destroy(ent)
            except Exception:
                pass
        self.open_dialog_entities = []

    def _apply_open(self, prefab_id: str) -> None:
        self._close_open_dialog()
        for p in list(self.pieces):
            self._remove_piece(p)
        self.meta = PrefabState(prefab_id=prefab_id)
        self._load_from_disk(prefab_id)
        self._instantiate_pending_pieces()
        self._set_title()
        self._refresh_status()
        self._show_toast(f"opened: {prefab_id}")

    # ------------------------------------------------------------------
    # World: spawn / select / delete
    # ------------------------------------------------------------------
    def _spawn_piece_core(
        self,
        *,
        rel: str,
        pos: tuple[float, float, float],
        rot_y: float,
        scale: tuple[float, float, float],
        select: bool,
        texture_override: str | None = None,
        texture_override_mode: str | None = None,
    ) -> PlacedPiece | None:
        from ursina import Entity, Vec3, scene
        abs_path = self.assets_models / rel
        if not abs_path.is_file():
            self._show_toast(f"missing: {rel}", err=True)
            return None
        node = _load_model_node_from_file(abs_path)
        if node is None:
            self._show_toast(f"load failed: {rel}", err=True)
            return None
        pf = pack_extent_multiplier_for_rel(rel)
        ent = Entity(
            parent=scene,
            model=node,
            collider="box",
            double_sided=True,
            position=Vec3(pos[0], pos[1], pos[2]),
            rotation_y=rot_y,
            scale=Vec3(
                scale[0] * pf,
                scale[1] * pf,
                scale[2] * pf,
            ),
        )
        try:
            _apply_gltf_color_and_shading(ent.model, debug_materials=False, model_label=rel)
            apply_kenney_pack_color_tint_to_entity(ent, rel)
        except Exception as exc:
            print(f"[assembler] shader classify failed for {rel}: {exc!r}")
        apply_prefab_texture_override(ent, texture_override, texture_override_mode)
        ent.assembler_role = "piece"
        piece = PlacedPiece(
            model_rel=rel,
            entity=ent,
            pos=pos,
            rot_y=rot_y,
            scale=scale,
            texture_override=str(texture_override) if texture_override else None,
            texture_override_mode=str(texture_override_mode) if texture_override_mode else None,
        )
        ent.assembler_piece_ref = piece
        self.pieces.append(piece)
        if select:
            self._set_selection(piece)
        self._refresh_status()
        return piece

    def _try_place_at_world_point(self, world_x: float, world_z: float) -> None:
        if not self.current_piece_rel:
            self._show_toast("pick a library piece first", err=True)
            return
        x = _snap(world_x, GRID_CELL)
        z = _snap(world_z, GRID_CELL)
        y = float(self.meta.ground_anchor_y)
        self._spawn_piece_core(
            rel=self.current_piece_rel,
            pos=(x, y, z),
            rot_y=0.0,
            scale=(1.0, 1.0, 1.0),
            select=True,
        )

    def _set_selection(self, piece: PlacedPiece | None) -> None:
        from ursina import Entity, Mesh, Vec3, color, scene
        from ursina.shaders import unlit_shader

        if self.selection_marker is not None:
            try:
                self.selection_marker.enabled = False
                from ursina import destroy
                destroy(self.selection_marker)
            except Exception:
                pass
            self.selection_marker = None

        self.selected = piece
        if piece is None or piece.entity is None:
            self._refresh_status()
            return

        # Wireframe bounding cube around the selection.
        try:
            tb = piece.entity.model.getTightBounds() if piece.entity.model is not None else None
        except Exception:
            tb = None
        if tb:
            pmin, pmax = tb
            mx = 0.5 * (pmin.x + pmax.x)
            my = 0.5 * (pmin.y + pmax.y)
            mz = 0.5 * (pmin.z + pmax.z)
            dx = float(pmax.x - pmin.x) + 0.10
            dy = float(pmax.y - pmin.y) + 0.10
            dz = float(pmax.z - pmin.z) + 0.10
        else:
            mx = my = mz = 0.0
            dx = dy = dz = 1.1

        # 12 edges of a box in local space.
        hx, hy, hz = dx * 0.5, dy * 0.5, dz * 0.5
        corners = [
            Vec3(-hx, -hy, -hz), Vec3(+hx, -hy, -hz),
            Vec3(+hx, -hy, +hz), Vec3(-hx, -hy, +hz),
            Vec3(-hx, +hy, -hz), Vec3(+hx, +hy, -hz),
            Vec3(+hx, +hy, +hz), Vec3(-hx, +hy, +hz),
        ]
        edges = [
            (0, 1), (1, 2), (2, 3), (3, 0),
            (4, 5), (5, 6), (6, 7), (7, 4),
            (0, 4), (1, 5), (2, 6), (3, 7),
        ]
        verts: list = []
        for a, b in edges:
            verts.append(corners[a])
            verts.append(corners[b])
        self.selection_marker = Entity(
            parent=piece.entity,
            position=Vec3(mx, my, mz),
            model=Mesh(vertices=verts, mode="line", thickness=2.5),
            color=color.yellow,
            collision=False,
            shader=unlit_shader,
        )
        self._refresh_status()

    def _remove_piece(self, piece: PlacedPiece) -> None:
        if self.selected is piece:
            self._set_selection(None)
        try:
            if piece.entity is not None:
                piece.entity.enabled = False
                from ursina import destroy
                destroy(piece.entity)
        except Exception:
            pass
        try:
            self.pieces.remove(piece)
        except ValueError:
            pass
        self._refresh_status()

    # -- nudge / rotate / y ---------------------------------------------
    def _move_selected(self, dx: float, dz: float, dy: float = 0.0) -> None:
        if self.selected is None or self.selected.entity is None:
            return
        x, y, z = self.selected.pos
        self.selected.pos = (x + dx, y + dy, z + dz)
        self.selected.entity.position = (x + dx, y + dy, z + dz)
        self._refresh_status()

    def _rotate_selected(self, d_deg: float) -> None:
        if self.selected is None or self.selected.entity is None:
            return
        self.selected.rot_y = (self.selected.rot_y + d_deg) % 360.0
        self.selected.entity.rotation_y = self.selected.rot_y
        self._refresh_status()

    def apply_piece_scale_to_entity(self, piece: PlacedPiece) -> None:
        """Set ``entity.scale`` from logical ``piece.scale`` and Kenney pack extent multiplier."""
        if piece.entity is None:
            return
        from ursina import Vec3

        rel = piece.model_rel
        pf = pack_extent_multiplier_for_rel(rel)
        s = piece.scale
        piece.entity.scale = Vec3(
            s[0] * pf,
            s[1] * pf,
            s[2] * pf,
        )

    def _nudge_selected_scale(self, grow: bool, *, fine: bool) -> None:
        """Multiplicative uniform scale nudge on logical `PlacedPiece.scale` (saved to JSON)."""
        if self.selected is None:
            self._show_toast("no piece selected", err=True)
            return
        if self.selected.entity is None:
            return
        base = SCALE_NUDGE_FACTOR_FINE if fine else SCALE_NUDGE_FACTOR
        factor = base if grow else (1.0 / base)
        s0, s1, s2 = self.selected.scale
        self.selected.scale = (
            min(SCALE_LOGICAL_MAX, max(SCALE_LOGICAL_MIN, s0 * factor)),
            min(SCALE_LOGICAL_MAX, max(SCALE_LOGICAL_MIN, s1 * factor)),
            min(SCALE_LOGICAL_MAX, max(SCALE_LOGICAL_MIN, s2 * factor)),
        )
        self.apply_piece_scale_to_entity(self.selected)
        self._refresh_status()

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------
    def _install_input_hook(self) -> None:
        import __main__
        __main__.input = self.handle_input

    def handle_input(self, key: str) -> None:
        from ursina import application, held_keys, mouse

        def _shift_held() -> bool:
            return bool(held_keys.get("shift", 0) or held_keys.get("left shift", 0))

        def _control_held() -> bool:
            return bool(
                held_keys.get("left control", 0)
                or held_keys.get("right control", 0)
            )

        # ESC: only dismiss modals / the open-prefab dialog. Does not exit (avoids
        # accidental data loss; use Ctrl+Q to quit).
        if key == "escape":
            if (self.modal_field is not None) or self.open_dialog_entities:
                self._close_modal()
                self._close_open_dialog()
            return

        # Left mouse down: route to UI, ground, or piece.
        if key == "left mouse down":
            self._handle_left_click()
            return

        # Keyboard actions always operate on the current selection.
        if key in ("delete", "backspace"):
            if self.selected is not None:
                self._remove_piece(self.selected)
            return

        # Ctrl+Q: quit. (Plain Q = rotate, below.) Some platforms send a combined name.
        if key in ("control-q", "ctrl-q") or (key == "q" and _control_held()):
            try:
                application.quit()
            except Exception:
                sys.exit(0)
            return

        xz_step = NUDGE_FINE_STEP if _shift_held() else NUDGE_STEP
        if key == "w":
            self._move_selected(0.0, +xz_step)
            return
        if key == "s":
            self._move_selected(0.0, -xz_step)
            return
        if key == "a":
            self._move_selected(-xz_step, 0.0)
            return
        if key == "d":
            self._move_selected(+xz_step, 0.0)
            return
        if key == "q":
            self._rotate_selected(+ROT_STEP)
            return
        if key == "e":
            self._rotate_selected(-ROT_STEP)
            return
        if key == "[":
            y_step = Y_STEP_FINE if _shift_held() else Y_STEP
            self._move_selected(0.0, 0.0, dy=-y_step)
            return
        if key == "]":
            y_step = Y_STEP_FINE if _shift_held() else Y_STEP
            self._move_selected(0.0, 0.0, dy=+y_step)
            return

        fine_scale = _shift_held()
        # Panda/Ursina: main keyboard '-', '='; also accept common aliases.
        if key in ("-", "minus", "subtract"):
            self._nudge_selected_scale(grow=False, fine=fine_scale)
            return
        if key in ("=", "equals"):
            self._nudge_selected_scale(grow=True, fine=fine_scale)
            return

    def _handle_left_click(self) -> None:
        from ursina import mouse
        hovered = getattr(mouse, "hovered_entity", None)

        # If clicking a UI element, Ursina already dispatched the on_click; bail.
        if hovered is not None and getattr(hovered, "parent", None) is not None:
            # UI elements live under camera.ui.
            try:
                from ursina import camera
                if self._is_ui_descendant(hovered, camera.ui):
                    return
            except Exception:
                pass

        # Clicking an existing placed piece -> select it.
        if hovered is not None and getattr(hovered, "assembler_role", None) == "piece":
            piece = getattr(hovered, "assembler_piece_ref", None)
            if piece is not None:
                self._set_selection(piece)
                return

        # Clicking the ground slab -> place new piece at snapped hit point.
        if hovered is not None and getattr(hovered, "assembler_role", None) == "ground":
            wp = getattr(mouse, "world_point", None)
            if wp is not None:
                self._try_place_at_world_point(float(wp.x), float(wp.z))
            return

    @staticmethod
    def _is_ui_descendant(ent: Any, ui_root: Any) -> bool:
        cur = ent
        for _ in range(32):
            if cur is ui_root:
                return True
            cur = getattr(cur, "parent", None)
            if cur is None:
                return False
        return False

    # ------------------------------------------------------------------
    # HUD helpers
    # ------------------------------------------------------------------
    def _set_title(self) -> None:
        try:
            from ursina import window
            window.title = f"Kingdom Sim - Kenney Kit Assembler ({self.meta.prefab_id})"
        except Exception:
            pass

    def _refresh_status(self) -> None:
        if self.status_text is None:
            return
        sel_str = "(none)"
        if self.selected is not None:
            x, y, z = self.selected.pos
            sx, sy, sz = self.selected.scale
            sel_str = (
                f"{Path(self.selected.model_rel).name}"
                f"  pos=({x:+.2f},{y:+.2f},{z:+.2f})"
                f"  rot_y={self.selected.rot_y:.0f}"
                f"  scale=({sx:.2f},{sy:.2f},{sz:.2f})"
            )
        self.status_text.text = (
            f"pieces: {len(self.pieces)}   selected: {sel_str}"
        )
        if self.current_meta_label is not None:
            self.current_meta_label.text = (
                f"id={self.meta.prefab_id}  type={self.meta.building_type}  "
                f"WxD={self.meta.footprint_tiles[0]}x{self.meta.footprint_tiles[1]}  "
                f"attrib={','.join(self.meta.attribution) or '(auto)'}"
            )

    def _show_toast(self, msg: str, *, err: bool = False) -> None:
        if self.toast_text is None:
            return
        from ursina import color
        self.toast_text.text = msg
        self.toast_text.color = color.red if err else color.lime
        print(f"[assembler] {msg}")


# -- CLI ------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Kenney kit assembler (WK28 spike). Place .glb kit pieces on a 1-unit grid "
            "and save/reload building prefab JSON under assets/prefabs/buildings/."
        )
    )
    p.add_argument("--new", action="store_true", help="Start a fresh empty prefab.")
    p.add_argument("--open", dest="open_id", type=str, default=None,
                   help="Open an existing prefab by prefab_id (filename stem).")
    p.add_argument("--prefab-id", dest="prefab_id", type=str, default=None,
                   help="Initial prefab_id (filename stem) when using --new. Default: untitled_v1.")
    p.add_argument("--out-dir", type=str, default=str(DEFAULT_OUT_DIR),
                   help="Directory where prefab JSON files are written/read.")
    p.add_argument("--assets-models", type=str, default=str(ASSETS_MODELS),
                   help="Root folder for Kenney models (default: assets/models).")
    p.add_argument("--auto-exit-sec", type=float, default=0.0,
                   help="After this many seconds, save a screenshot and quit.")
    p.add_argument("--screenshot-subdir", type=str, default=None,
                   help="Subfolder under docs/screenshots/ for auto screenshots.")
    p.add_argument("--screenshot-stem", type=str, default=None,
                   help="Filename stem for auto screenshots.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not args.new and not args.open_id:
        print(
            "[assembler] No mode given; defaulting to --new with prefab_id=untitled_v1. "
            "Use --open <id> to edit an existing prefab.",
            file=sys.stderr,
        )
        args.new = True

    if args.new and args.open_id:
        print("[assembler] --new and --open are mutually exclusive.", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir).resolve()
    assets_models = Path(args.assets_models).resolve()
    if not assets_models.is_dir():
        print(f"[assembler] assets_models not found: {assets_models}", file=sys.stderr)
        return 1

    prefab_id = args.open_id or args.prefab_id or DEFAULT_PREFAB_ID
    open_existing = bool(args.open_id)

    app = AssemblerApp(
        assets_models=assets_models,
        out_dir=out_dir,
        prefab_id=prefab_id,
        open_existing=open_existing,
        auto_exit_sec=float(args.auto_exit_sec or 0.0),
        screenshot_subdir=args.screenshot_subdir,
        screenshot_stem=args.screenshot_stem,
    ).build()
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
