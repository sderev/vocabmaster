# GitHub Actions CI/CD Workflows

This directory contains the CI/CD pipeline configuration for VocabMaster.

## Workflows

### 1. CI (`ci.yml`)

**Triggers:** Push to `main`, Pull requests to `main`

**Jobs:**
* **Lint** - Runs `ruff` linter and format checker
* **Test** - Runs test suite across multiple Python versions (3.10, 3.11, 3.12) and OS (Ubuntu, macOS, Windows)
* **Build** - Builds the package distribution
* **Install Test** - Verifies the package can be installed and the CLI works

**Coverage:** Uploads coverage reports to Codecov (requires `CODECOV_TOKEN` secret)

### 2. Release (`release.yml`)

**Triggers:** Git tags matching `v*` (e.g., `v0.2.1`)

**Jobs:**
* **Test** - Runs full test suite before release
* **Build** - Builds distribution packages (wheel and sdist)
* **Publish to PyPI** - Publishes package to PyPI using trusted publishing
* **Create GitHub Release** - Creates a GitHub release with auto-generated changelog

**Required Setup:**
1. Configure PyPI trusted publishing:
   * Go to https://pypi.org/manage/account/publishing/
   * Add GitHub as a trusted publisher for this repository
   * Specify the workflow: `release.yml`
   * Specify the environment: `pypi`

2. The workflow uses GitHub's OIDC token for authentication (no API token needed)

### 3. Dependency Check (`dependencies.yml`)

**Triggers:**
* Weekly schedule (Mondays at 9:00 UTC)
* Manual dispatch

**Jobs:**
* Checks for outdated dependencies
* Creates or updates a GitHub issue with outdated packages

### 4. Security Scan (`security.yml`)

**Triggers:**
* Push to `main`, Pull requests to `main`
* Daily schedule (2:00 UTC)
* Manual dispatch

**Jobs:**
* **Dependency Scan** - Uses `pip-audit` and `safety` to detect vulnerable dependencies
* **Secret Scan** - Uses Gitleaks to detect leaked credentials
* **CodeQL Analysis** - GitHub semantic security vulnerability analysis

The standalone security workflow provides daily automated scans for newly disclosed vulnerabilities.

## Manual Workflow Triggers

You can manually trigger workflows from the Actions tab:

```bash
# Using GitHub CLI
gh workflow run ci.yml
gh workflow run dependencies.yml
gh workflow run security.yml
```

## Creating a Release

To create a new release:

1. Update the version in `pyproject.toml`
2. Commit the changes
3. Create and push a tag:
   ```bash
   git tag v0.2.1
   git push origin v0.2.1
   ```
4. The release workflow will automatically:
   * Run tests
   * Build the package
   * Publish to PyPI
   * Create a GitHub release

## Status Badges

Add these badges to your README.md:

```markdown
[![CI](https://github.com/sderev/vocabmaster/actions/workflows/ci.yml/badge.svg)](https://github.com/sderev/vocabmaster/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/sderev/vocabmaster/graph/badge.svg)](https://codecov.io/gh/sderev/vocabmaster)
```

## Local Testing

Test the CI pipeline locally before pushing:

```bash
# Lint and format check
uv run ruff check .
uv run ruff format --check .

# Run tests
uv run pytest -v

# Run tests with coverage
uv run pytest --cov=vocabmaster --cov-report=term

# Build package
uv build

# Test installation
uv pip install dist/*.whl
vocabmaster --help
```

## Troubleshooting

### Coverage Upload Fails
* Ensure `CODECOV_TOKEN` secret is set in repository settings
* The workflow continues even if upload fails (`fail_ci_if_error: false`)

### PyPI Publishing Fails
* Verify trusted publishing is configured correctly on PyPI
* Check the `pypi` environment is configured in repository settings
* Ensure the tag format matches `v*` pattern

### Security Scan Issues
* Security scans run daily at 2:00 UTC to detect newly disclosed vulnerabilities
* Review security scan results in the Actions tab under `security.yml`
* Dependency scans use `pip-audit` and `safety` for vulnerability detection
* Secret scanning uses Gitleaks to detect leaked credentials
* CodeQL provides semantic analysis for security issues
* Update dependencies if vulnerabilities are found
