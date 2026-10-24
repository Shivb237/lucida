"""Verify that Sheet.tsx renders the pink grease-circle SVG in the correct places.

The grease SVG (stroke="var(--mag-film)", class="grease") must appear in:
  - ContactSheet: conditionally, for picked items (existing behaviour, must remain).
  - Print: unconditionally, for every selected outfit item (restored in this release).

This test reads source directly so it catches regressions even without a browser.
"""
import pathlib
import re

SHEET = (pathlib.Path(__file__).resolve().parents[1]
         / "web" / "src" / "components" / "Sheet.tsx")


def _source() -> str:
    return SHEET.read_text()


def test_grease_svg_present_in_print_component():
    src = _source()
    # Locate the Print function body
    m = re.search(r"export function Print\b.*?(?=\nexport function|\Z)", src, re.S)
    assert m, "Print component not found in Sheet.tsx"
    print_body = m.group(0)
    assert 'className="grease"' in print_body, (
        'The grease SVG is missing from Print — the pink outfit-selection indicator '
        'must be present on every board figure.'
    )
    assert 'stroke="var(--mag-film)"' in print_body, (
        'The grease SVG path must use var(--mag-film) for the pink colour.'
    )
    assert "position: 'relative'" in print_body, (
        "Each Print board figure must have a position:relative wrapper "
        "so the absolutely-positioned grease SVG overlays the image correctly."
    )
    assert 'aria-hidden="true"' in print_body, (
        "The grease SVG must be aria-hidden in Print."
    )


def test_grease_svg_still_present_in_contact_sheet():
    """ContactSheet behaviour must be unchanged: the ring is conditional on picked.has(h.id)."""
    src = _source()
    m = re.search(r"export function ContactSheet\b.*?(?=\nexport function|\Z)", src, re.S)
    assert m, "ContactSheet component not found in Sheet.tsx"
    cs_body = m.group(0)
    assert 'className="grease"' in cs_body, "ContactSheet must still render the grease SVG."
    assert "picked.has(h.id)" in cs_body, (
        "ContactSheet must still show the ring only for picked items."
    )


def test_circles_and_hash_still_defined():
    src = _source()
    assert "const CIRCLES" in src, "CIRCLES path-data array must remain defined."
    assert "const hash" in src, "hash() helper must remain defined."
