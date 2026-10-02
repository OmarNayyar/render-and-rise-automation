# Local configuration

Runtime configuration is intentionally external to source control. Copy `.env.example` to `.env`, add local credentials, and copy `sample_data/products_queue.sample.csv` to `data/products_queue.csv`.

`RR_QUEUE_CSV` and `RR_PRODUCTS_DIR` can point the GUI at different local locations. Upscayl is discovered from `UPSCAYL_CLI` and `UPSCAYL_MODELS_DIR`, with standard Windows installation paths used as fallbacks.
