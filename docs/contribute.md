# How to contribute

Contributions are always appreciated.

How to:
* [Submit Pull Request](#pull-request)
* [Fix Formatting](#fix-formatting)
* [Squash Commits](#squash-commits)
* [Rebase Upstream](#rebase-with-upstream)

## Pull request

In order to submit a change or a PR, please fork the project and follow these instructions:
```bash
$ git clone http://github.com/<me>/krkn
$ cd krkn
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
We encourage our contributors to follow the same pattern while contributing to the code.

The pre-commit configuration file is present in the repository `.pre-commit-config.yaml`.
It contains the different code styling and linting guides which we use for the application.

The following command can be used to run the pre-commit:
`pre-commit run --all-files`

If pre-commit is not installed in your system, it can be installed with `pip install pre-commit`.

## Squash Commits
If there are multiple commits, please rebase/squash multiple commits
before creating the PR by following:

```bash
$ git checkout <my-working-branch>
$ git rebase -i HEAD~<num_of_commits_to_merge>
   -OR-
$ git rebase -i <commit_id_of_first_change_commit>
```

In the interactive rebase screen, set the first commit to `pick`, and all others to `squash`, or whatever else you may need to do.


Push your rebased commits (you may need to force), then issue your PR.

```
$ git push origin <my-working-branch> --force
```

## Rebase with Upstream

If changes go into the main repository while you're working on your code it is best to rebase your code with the
 upstream, so you stay up to date with all changes and fix any conflicting code changes.

If not already configured, set the upstream url for kraken.
```
 git remote add upstream https://github.com/krkn-chaos/krkn.git
```

Rebase to upstream master branch.
```
git fetch upstream
git rebase upstream/master
git push origin <branch_name> --force
```

If any errors occur, it will list off any files that have merge issues.
Edit the files with the code you want to keep. See below for detailed help from Git.
1. Vi <file(s)>
2. Resolving-a-merge-conflict-using-the-command-line
3. git add <all files you edit>
4. git rebase --continue
5. Might need to repeat steps 2 through 4 until rebase complete
6. git status <this will also tell you if you have other files to edit>
7. git push origin <branch_name> --force  [push the changes to github remote]


Merge Conflicts Example
```
1. git rebase upstream/kraken
2. vi run_kraken.py [edit at the indicated places, get rid of arrowed lines and dashes, and apply correct changes]
3. git add run_kraken.py
4. git rebase --continue
5. repeat 2-4 until done
6. git status <this will also tell you if you have other files to edit>
7. git push origin <branch_name> --force  [push the changes to github remote]
```
