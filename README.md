# render-farm
Push a job zip to `jobs/` on this branch. The `render` workflow renders it on 20 free GitHub runners in parallel and publishes `out/<name>.mp4` on branch `render-out`. See the header of `.github/workflows/render.yml` for the zip layout.
