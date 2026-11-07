# Releasing TuneTune

A release is one version number shared by every channel. Skills (`npx skills`), the Claude Code plugin and the Codex plugin read the repository directly, so whatever is on `main` is what new users install; CI on every push and pull request keeps `main` releasable. The `dsh-tunetune` npm package and the GitHub release are produced by pushing a tag.

## One-time setup

1. **npm account.** Create or sign in to the npm account that will own `dsh-tunetune`, with two-factor authentication on.
2. **First publish.** npm trusted publishing is configured from an existing package's settings, so the first version needs a token: create a granular access token with read and write access to packages, then add it as the repository secret `NPM_TOKEN` (Settings → Secrets and variables → Actions). Alternatively run `npm login` and `npm publish --access public` once from a clean checkout of the tag.
3. **Trusted publishing.** On npmjs.com open `dsh-tunetune` → Settings → Trusted publisher → GitHub Actions, and enter owner `nanshine`, repository `tunetune`, workflow `release.yml`, environment `npm`. Then delete the `NPM_TOKEN` secret and the token; later releases authenticate through GitHub's OIDC and carry provenance.
4. **Optional protection.** The publish job runs in the GitHub environment `npm`, created automatically on first use. Add required reviewers to it under Settings → Environments when a release should wait for approval.

## Each release

1. Bump the version everywhere it lives. `python3 scripts/check-release.py --tag v<new>` lists each place that still differs: both `package.json` files and `workspace/package-lock.json`, both plugin manifests, `VERSION` in `scripts/build-skills.py`, `init.py` and `records.py`, and the `resources.py` User-Agent; also update the pinned versions in `tests/test_distribution.py`, which the test suite will flag. A new tool version means existing studies stay pinned to the old one, as described in `AGENTS.md`.
2. Rebuild and test from the repository root:

   ```sh
   npm --prefix workspace run build
   python3 scripts/build-skills.py
   npm --prefix workspace test
   python3 -B -m unittest discover -s tests -v
   python3 scripts/check-release.py --tag v<new>
   ```

3. Commit, push `main` and wait for CI to pass.
4. Tag and push: `git tag v<new> && git push origin v<new>`.

The Release workflow reruns the full CI, refuses a tag that disagrees with any shipped version or license, publishes the npm package (`latest`, or `next` for a version with a pre-release suffix such as `0.8.0-rc.1`), and creates the GitHub release with generated notes and the npm tarball attached. Rerunning a failed release skips an already published npm version and updates the existing GitHub release.

## License

TuneTune is licensed under the Apache License 2.0. The root `LICENSE` and `NOTICE` ship in the npm package, and each skill folder carries `LICENSE.txt` and a `license` frontmatter field because skill installers copy one folder at a time. `scripts/check-release.py` fails when a copy drifts from the root file.
