# Contributing

## Development setup

```bash
pnpm install
pnpm run build
pnpm run build:zip   # local ZIP in out/
```

## Pull requests

1. Branch from `main`.
2. Keep changes focused; run `pnpm run build` before opening PR.
3. CI builds the plugin ZIP automatically (`.github/workflows/build-plugin.yml`).

## Releases (maintainers)

1. Update `CHANGELOG.md`.
2. Bump `version` in `package.json`.
3. Commit, tag, and push:

```bash
git tag v0.1.0
git push origin v0.1.0
```

GitHub Actions attaches `map-storage-v0.1.0.zip` to the release.

Manual run: **Actions → Release → Run workflow**.
