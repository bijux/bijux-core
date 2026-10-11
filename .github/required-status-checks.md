# Required Status Checks

- Owner: `build-and-release`
- Source of truth: workflow and job names in `.github/workflows/*.yml`

Required branch-protection checks for `main`:

- `policy / github` (from workflow `repository policy`)
- `policy / pr approval` (from workflow `pull request approval`)
- `std / standard` (from workflow `bijux-std`)
- `std / report` (from workflow `bijux-std`)

Notes:

- Treat these four checks as the baseline for all governed repos in the unified contract.
- Add repository-specific checks on top of this baseline only when they run on every human verification pull request for that repository.
- If workflow or job names change, update this file and `.github/rulesets/main-branch-protection.json` in the same change.
- Main branch bypass is not allowed; changes must merge through pull requests.
- For `pull_request_target` workflows, GitHub evaluates workflow content from the base branch, not from the pull request head branch.

Dependency proposals use the distinct `dependency / owner review notice` check.
It records that verification did not run and does not authorize a merge.
Dependency proposal jobs are excluded before allocation and use `unverified dependency /`
names, so skipped jobs cannot satisfy the required verification contexts.
Owners consolidate dependency intent into a qualified human pull request;
shared automation never enables automatic merging of dependency proposals.

Repositories declaring `main_verification: accepted-pull-request` verify the
human pull request once and retain GitHub's native manifest/lockfile dependency
graph updates after merge. Manual publication binds current `main` to its exact
normal merge and verified PR head, including owner approval. Masterclass keeps
its separately declared existing human events and documentation runtime.
