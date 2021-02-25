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
You can do this before your first commit but please take a look at the formatting outlined using tox.

To run:

```pip install tox ```(if not already installed)

```tox``` 

Fix all spacing, import issues and other formatting issues

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



