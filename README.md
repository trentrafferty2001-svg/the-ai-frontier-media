# GPU render jobs (Ancient Explained)

- `jobs/<name>.zip`: one engine folder (render.mjs, index.html, src/, fonts/) + job.json + mix WAVs.
- `order.json`: render order.
- `colab_worker.py`: run on a Colab T4. Renders each job not yet DONE/FAILED in `status.txt`,
  pushes `videos/<name><suffix>.mp4` to the `videos` branch, logs to `logs/<name>.log`.
- To re-render a job, push a zip with a new name (e.g. -v3b).
