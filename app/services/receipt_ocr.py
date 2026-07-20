"""Extract purchasable line items from German supermarket receipts."""

import re
import shutil
from decimal import Decimal, InvalidOperation
from pathlib import Path


PRICE = r"[0-9@]+[,.][0-9]{2}"


def _money(value):
    try:
        return Decimal(value.replace("@", "0").replace(",", ".")).quantize(Decimal("0.01"))
    except (InvalidOperation, AttributeError):
        return None


def parse_receipt_text(text):
    """Return editable rows with quantity, unit price, and line total."""
    items = []
    for raw_line in (text or "").splitlines():
        line = " ".join(raw_line.strip().split())
        if not line:
            continue
        lowered = line.casefold()
        if any(marker in lowered for marker in ("zu zahlen", "summe", "kreditkarte", "bezahlung")):
            if items:
                break
            continue

        quantity_match = re.match(
            rf"^(?P<name>.+?)\s+(?P<unit>{PRICE})\s+x\s+(?P<quantity>\d+)\s+(?P<total>{PRICE})(?:\s+[A-Z])?$",
            line,
            re.IGNORECASE,
        )
        if quantity_match:
            unit = _money(quantity_match.group("unit"))
            line_total = _money(quantity_match.group("total"))
            quantity = int(quantity_match.group("quantity"))
            if unit and line_total and 0 < quantity <= 50:
                # OCR commonly turns 0,69 into 6,69. The printed line total is
                # a second source of truth, so use it to repair an impossible
                # unit-price reading (for example 6.69 × 2 beside total 1.38).
                expected_total = (unit * quantity).quantize(Decimal("0.01"))
                if abs(expected_total - line_total) > Decimal("0.02"):
                    unit = (line_total / quantity).quantize(Decimal("0.01"))
                name = quantity_match.group("name").strip(" .-")
                items.append({"name": name, "quantity": quantity,
                              "unit_price": unit, "price": line_total})
            continue

        item_match = re.match(
            rf"^(?P<name>.+?)\s+(?P<price>{PRICE})(?:\s+[A-Z])?$", line, re.IGNORECASE
        )
        if not item_match:
            continue
        name = item_match.group("name").strip(" .-")
        price = _money(item_match.group("price"))
        if not price or price <= 0 or not re.search(r"[A-Za-zÄÖÜäöüß]", name):
            continue
        if any(word in name.casefold() for word in ("eur", "mwst", "netto", "brutto", "betrag")):
            continue
        items.append({"name": name, "quantity": 1, "unit_price": price, "price": price})
    return items


def scan_image(file_storage):
    """OCR an uploaded receipt image and return parsed product rows."""
    from PIL import Image, ImageOps
    import pytesseract

    # Desktop apps and IDE-launched Flask processes do not always inherit the
    # shell PATH. Locate Homebrew/system Tesseract explicitly when necessary.
    executable = shutil.which("tesseract")
    if not executable:
        executable = next((str(path) for path in (
            Path("/opt/homebrew/bin/tesseract"),
            Path("/usr/local/bin/tesseract"),
            Path("/usr/bin/tesseract"),
        ) if path.exists()), None)
    if not executable:
        raise RuntimeError("The Tesseract OCR engine is not installed or could not be found.")
    pytesseract.pytesseract.tesseract_cmd = executable

    image = Image.open(file_storage.stream)
    image = ImageOps.autocontrast(ImageOps.grayscale(image))
    # Digital Lidl receipts are often very tall but only ~450 px wide. Upscale
    # them before OCR so punctuation and decimal commas remain legible.
    if image.width < 1200:
        scale = min(3, 1200 / image.width)
        image = image.resize((int(image.width * scale), int(image.height * scale)))
    image.thumbnail((3000, 9000))
    try:
        attempts = ("eng+deu", "deu", "eng")
        text = ""
        last_error = None
        for language in attempts:
            try:
                text = pytesseract.image_to_string(image, lang=language, config="--psm 6")
                if parse_receipt_text(text):
                    break
            except (pytesseract.TesseractError, pytesseract.TesseractNotFoundError) as error:
                last_error = error
        if not text and last_error:
            raise last_error
    finally:
        file_storage.stream.seek(0)
    return parse_receipt_text(text)
