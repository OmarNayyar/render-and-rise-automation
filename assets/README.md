# Runtime assets

- A local `delivery_template.docx` can provide the `{{TITLE}}` and `{{DROPBOX_LINK}}` placeholders used by the delivery-PDF stage.
- A local `README-HowToPrint.pdf` can be copied into each customer export package.
- `mockup_templates/` is intentionally not populated with production templates. Add assets you own or are licensed to redistribute before generating new mockups.

These production documents are excluded because the originals contain storefront/contact details. For a calibrated mockup named `m01.png`, add matching `mockup_templates/calibration/m01_red.png` and `m01_green.png` images. The renderer derives the placement mask and lighting model from their pixel-level differences.
