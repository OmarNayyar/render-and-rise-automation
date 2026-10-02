# Mockup template contract

Production mockup source files are not redistributed in this public repository.

For each template, provide:

```text
assets/mockup_templates/
├── m01.png
└── calibration/
    ├── m01_red.png
    └── m01_green.png
```

The base, red, and green files must have identical dimensions. Pixels outside the printable surface must remain identical in both calibration images. Inside the printable surface, use exact red (`#FF0000`) and green (`#00FF00`) reference fills so the renderer can recover the placement mask, shading, and ambient light.
