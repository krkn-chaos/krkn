# How to contribute

Contributions are always appreciated.

How to:
* [Submit Pull Request](#pull-request)
* [Fix Formatting](#fix-formatting)
* [Squash Commits](#squash-commits)

## Pull request

In order to submit a change or a PR, please fork the project and follow instructions:
```bash
$ git clone http://github.com/<me>/kraken
$ cd kraken
$ git checkout -b <branch_name>
$ <make change>
$ git add <changes>
$ git commit -a
$ <insert good message>
$ git push
```

## Fix Formatting
Kraken uses [pre-commit](https://pre-commit.com) framework to maintain the code linting and python code styling.
The CI would run the pre-commit check on each pull request.
We encourage our contributors to follow the same pattern, while contributing to the code.

The pre-commit configuration file is present in the repository `.pre-commit-config.yaml`
It contains the different code styling and linting guide which we use for the application.

Following command can be used to run the pre-commit:
`pre-commit run --all-files`

If pre-commit is not installed in your system, it can be install with : `pip install pre-commit`

## Squash Commits
If there are mutliple commits, please rebase/squash multiple commits
before creating the PR by following:

```bash
$ git checkout <my-working-branch>
$ git rebase -i HEAD~<num_of_commits_to_merge>
   -OR-
$ git rebase -i <commit_id_of_first_change_commit>
```

In the interactive rebase screen, set the first commit to `pick` and all others to `squash` (or whatever else you may need to do).

Push your rebased commits (you may need to force), then issue your PR.

```
$ git push origin <my-working-branch> --force
```
