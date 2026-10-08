# Releasing

The suite version lives in `VERSION`. Individual skills keep their own versions in `SKILL.md`; they do not need to match the suite version.

1. Update `VERSION`, `CHANGELOG.md`, and any changed skill versions. Keep both READMEs aligned.
2. Run `python3 -m unittest discover -s tests -v` with FFmpeg / ffprobe available. Verify skill entry points and relevant installation paths. Commit and push only the intended files, then wait for Checks to pass.
3. Create a tag matching `VERSION`, for example `v0.5.0`, at the verified commit. Never move an existing published tag.
4. Build the ZIP from the tag, not the working directory:

```bash
mkdir -p dist
git archive --format=zip --prefix=video-circus-0.5.0/ --output=dist/video-circus-0.5.0.zip v0.5.0
python3 - <<'PY'
from pathlib import Path
import hashlib
p = Path('dist/video-circus-0.5.0.zip')
p.with_name('SHA256SUMS.txt').write_text(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n')
PY
```

5. Inspect the archive: all four complete skill directories, their licenses, scripts, references, agent metadata, and the HTML template must be present. Reject private media, model weights, account data, caches, and generated reports. Smoke-test the extracted scripts.
6. Publish a GitHub Release with parallel English and Chinese notes, the ZIP, and `SHA256SUMS.txt`. The ZIP contains the tagged project source; GitHub also provides automatic source archives. Runtime tools and speech models are installed separately.
7. Download the release assets, check their SHA-256, compare ZIP entries with the tagged source, and confirm the release tag and default branch point to the intended commits.

The first public release is `v0.5.0`. Earlier development milestones are recorded in `docs/validation.md`, not published as retroactive releases. Regression CI does not download real platform videos or run model inference; those checks require separate evidence.
