"""Generate default animal advocacy persona profiles for browser QA.

Creates persona YAML files in .desloppify/personas/ that represent
the key user types in the animal liberation movement.
"""

from __future__ import annotations

from pathlib import Path

PERSONAS = [
    {
        "filename": "undercover-investigator.yaml",
        "content": """\
name: Undercover Investigator
description: >
  An undercover investigator documenting conditions at factory farms
  and slaughterhouses. Needs maximum operational security — metadata
  stripping on uploads, zero-retention on file transfers, no identity
  leakage through browser fingerprinting or session correlation.
device: desktop
viewport:
  width: 1024
  height: 768
scenarios:
  - goal: Upload investigation footage securely
    max_steps: 10
    checks:
      - File upload strips EXIF/GPS metadata before transmission
      - Upload endpoint uses zero-retention storage or E2E encryption
      - No analytics or telemetry fires during upload flow
      - Session cannot be correlated to previous visits
  - goal: Access encrypted communications channel
    max_steps: 8
    checks:
      - Communications page loads without third-party scripts
      - No external CDN resources that could log IP addresses
      - WebSocket or messaging connections use TLS
  - goal: Verify zero-retention on sensitive data submission
    max_steps: 6
    checks:
      - Form submission does not send data to third-party analytics
      - Server response headers indicate no caching of sensitive data
      - Browser storage (localStorage, sessionStorage) does not persist PII
accessibility_checks:
  - All interactive elements have visible focus indicators
  - Forms work without JavaScript (progressive enhancement)
severity_mapping:
  blocker: high
  usability: medium
  polish: low
""",
    },
    {
        "filename": "sanctuary-operator.yaml",
        "content": """\
name: Sanctuary Operator
description: >
  An operator at an animal sanctuary managing intake records,
  medical logs, and adoption applications for rescued farmed animals.
  Needs reliable data handling with location privacy for the facility.
device: desktop
viewport:
  width: 1440
  height: 900
scenarios:
  - goal: Manage animal intake records
    max_steps: 12
    checks:
      - Animal records use species-appropriate terminology (not livestock)
      - Sanctuary address is not exposed in page source or API responses
      - Medical data is encrypted at rest
      - Intake form validates required fields without exposing facility location
  - goal: Process adoption application
    max_steps: 10
    checks:
      - Adopter PII is handled with appropriate privacy controls
      - Application status updates do not leak sanctuary location
      - Email notifications use privacy-respecting headers
  - goal: Coordinate with veterinary partners
    max_steps: 8
    checks:
      - Shared medical records are access-controlled
      - Veterinary partner data does not leave the application boundary
accessibility_checks:
  - Data tables are screen-reader accessible with proper headers
  - Date pickers have keyboard-accessible alternatives
severity_mapping:
  blocker: high
  usability: medium
  polish: low
""",
    },
    {
        "filename": "grassroots-organizer.yaml",
        "content": """\
name: Grassroots Organizer (Rural)
description: >
  A grassroots animal rights organizer in a rural area with limited
  internet bandwidth. Uses mobile primarily. Needs the application
  to work on slow connections and small screens.
device: mobile
viewport:
  width: 375
  height: 667
network_throttle: 3g
scenarios:
  - goal: Sign up for an animal rights campaign
    max_steps: 8
    checks:
      - Signup form loads within 5 seconds on 3G connection
      - Form is usable on 375px viewport without horizontal scrolling
      - Validation errors are visible without scrolling
      - Campaign description uses anti-speciesist language throughout
  - goal: Share action alert on social media
    max_steps: 6
    checks:
      - Share functionality works on mobile browsers
      - Open Graph / social preview uses compassionate language and imagery
      - Share links do not contain tracking parameters that identify the sharer
  - goal: Access campaign resources offline
    max_steps: 6
    checks:
      - Key resources are available via service worker or offline cache
      - Offline state is communicated clearly to the user
accessibility_checks:
  - Touch targets are at least 44x44px
  - Text is readable without zooming (minimum 16px body text)
  - Images have alt text that reflects anti-speciesist values
severity_mapping:
  blocker: high
  usability: medium
  polish: low
""",
    },
    {
        "filename": "disabled-vegan-activist.yaml",
        "content": """\
name: Disabled Vegan Activist
description: >
  A vegan activist who uses a screen reader and keyboard-only
  navigation. Needs full accessibility compliance — every
  interactive element must be operable without a mouse.
device: desktop
viewport:
  width: 1280
  height: 720
accessibility_mode: true
scenarios:
  - goal: Navigate campaign pages with screen reader
    max_steps: 10
    checks:
      - All pages have logical heading hierarchy (h1 > h2 > h3)
      - Skip navigation link is present and functional
      - Images have descriptive alt text (not just filenames)
      - Dynamic content updates are announced to screen readers (aria-live)
  - goal: Fill out volunteer signup form
    max_steps: 8
    checks:
      - All form fields have associated labels (not just placeholders)
      - Error messages are programmatically associated with fields (aria-describedby)
      - Form can be submitted using only keyboard (Enter key)
      - Required fields are indicated both visually and programmatically
  - goal: Access video content with captions
    max_steps: 6
    checks:
      - Videos have closed captions or transcripts available
      - Video player controls are keyboard accessible
      - Autoplay is disabled or can be stopped immediately
accessibility_checks:
  - Color contrast meets WCAG AA (4.5:1 for normal text, 3:1 for large)
  - Focus order follows visual layout
  - No keyboard traps in interactive components
  - ARIA roles are used correctly (not just decoratively)
severity_mapping:
  blocker: high
  usability: medium
  polish: low
""",
    },
    {
        "filename": "non-english-supporter.yaml",
        "content": """\
name: Non-English Speaking Supporter
description: >
  A supporter of the global animal rights movement who primarily
  speaks Spanish, Hindi, or Portuguese. Tests internationalization
  completeness and cultural sensitivity in translations.
device: desktop
viewport:
  width: 1280
  height: 720
browser_language: es
scenarios:
  - goal: Understand campaign call to action in Spanish
    max_steps: 8
    checks:
      - Primary navigation is fully translated
      - Campaign call-to-action text is translated (not English fallback)
      - Dates and numbers use locale-appropriate formatting
      - Translated content uses culturally appropriate anti-speciesist terminology
  - goal: Navigate signup flow in non-English language
    max_steps: 8
    checks:
      - Form labels and validation messages are translated
      - Error messages appear in the selected language
      - Success confirmations are in the correct language
  - goal: Access translated content without broken layout
    max_steps: 6
    checks:
      - Longer translated strings do not overflow containers
      - RTL layout support (if applicable) does not break navigation
      - No untranslated strings visible in the UI
accessibility_checks:
  - Language attribute (lang) is set correctly on the html element
  - Translated alt text is provided for images
severity_mapping:
  blocker: high
  usability: medium
  polish: low
""",
    },
]

_README_CONTENT = """\
# Persona QA Profiles

These are the default animal advocacy persona profiles generated by desloppify.
Each YAML file represents a user type in the animal liberation movement.

## Personas

- **Undercover Investigator** — Maximum operational security for factory farm investigations
- **Sanctuary Operator** — Data handling and location privacy for animal rescue facilities
- **Grassroots Organizer (Rural)** — Mobile-first, low-bandwidth for rural activists
- **Disabled Vegan Activist** — Full accessibility compliance, screen reader and keyboard-only
- **Non-English Speaking Supporter** — Internationalization and cultural sensitivity

## Customizing

Edit these files to match your project's specific user journeys. Key fields:

- `scenarios[].goal` — What the persona is trying to accomplish
- `scenarios[].checks` — Specific things to verify during the test
- `accessibility_checks` — WCAG and usability checks for this persona
- `viewport` — Screen size for this persona's device

## Adding Project-Specific Personas

Create a new YAML file in this directory following the same format.
Consider adding personas for:

- Your most common user type
- Users in regions with restrictive internet (censorship, filtering)
- Users on older devices or browsers
- Users who need to remain anonymous

## Running Persona QA

```bash
desloppify persona-qa --prepare --url <your-app-url>
# Follow the agent instructions to run browser tests
desloppify persona-qa --import findings.json
desloppify persona-qa --status
```
"""


def generate_default_personas(
    target_dir: Path | None = None,
    framework: str | None = None,
) -> Path:
    """Generate default animal advocacy persona profiles.

    Returns the directory where persona files were written.
    """
    if target_dir is None:
        target_dir = Path(".desloppify") / "personas"

    target_dir.mkdir(parents=True, exist_ok=True)

    for persona in PERSONAS:
        persona_path = target_dir / persona["filename"]
        if not persona_path.exists():
            persona_path.write_text(persona["content"], encoding="utf-8")

    readme_path = target_dir / "README.md"
    if not readme_path.exists():
        readme_path.write_text(_README_CONTENT, encoding="utf-8")

    return target_dir
