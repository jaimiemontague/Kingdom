from __future__ import annotations

import pygame

from game.graphics.animation import load_png_frames
from game.ui.widgets import _IMAGE_CACHE, load_image_cached


def test_load_png_frames_works_without_display(monkeypatch, tmp_path) -> None:
    pygame.init()
    try:
        (tmp_path / "frame_000.png").write_bytes(b"stub")
        sample = pygame.Surface((4, 4), pygame.SRCALPHA)

        monkeypatch.setattr(pygame.display, "get_surface", lambda: None)
        monkeypatch.setattr(pygame.image, "load", lambda path: sample.copy())

        frames = load_png_frames(tmp_path, scale_to=(8, 8))

        assert len(frames) == 1
        assert frames[0].get_size() == (8, 8)
    finally:
        pygame.quit()


def test_load_image_cached_works_without_display(monkeypatch, tmp_path) -> None:
    pygame.init()
    _IMAGE_CACHE.clear()
    try:
        image_path = tmp_path / "panel.png"
        image_path.write_bytes(b"stub")
        sample = pygame.Surface((5, 5), pygame.SRCALPHA)

        monkeypatch.setattr(pygame.display, "get_surface", lambda: None)
        monkeypatch.setattr(pygame.image, "load", lambda path: sample.copy())

        img = load_image_cached(str(image_path), size=(9, 7))

        assert img is not None
        assert img.get_size() == (9, 7)
    finally:
        _IMAGE_CACHE.clear()
        pygame.quit()
