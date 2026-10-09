# Type of change

- [ ] Refactor
- [ ] New feature
- [ ] Bug fix
- [ ] Optimization

# Description  
<-- Provide a brief description of the changes made in this PR. -->  

## Related Tickets & Documents
If there is no related issue, please create one and discuss the proposed change before opening this PR.

- Related Issue #: 
- Fixes #<issue-number>:

The PR description must include a GitHub closing reference such as `Fixes #1234` or `Closes #1234`.

# Documentation  
- [ ] **Is documentation needed for this update?**

If checked, a documentation PR must be created and merged in the [website repository](https://github.com/krkn-chaos/website/).

## Related Documentation PR (if applicable)  
<-- Add the link to the corresponding documentation PR in the website repository -->  

# Checklist before requesting a review
- [ ] I have linked this PR to an existing issue with `Fixes #<issue-number>` in the description.
- [ ] I am assigned to the linked issue and the linked issue has maintainer approval (`triage/accepted`) or is labeled `kind/bug`.
- [ ] I have discussed the changes and proposed solution in the relevant issue and received acknowledgment from the community or maintainers. See the [contributing guidelines](https://krkn-chaos.dev/docs/contribution-guidelines/). See [testing your changes](https://krkn-chaos.dev/docs/developers-guide/testing-changes/) and run on any Kubernetes or OpenShift cluster to validate your changes
- [ ] I have performed a self-review of my code by running krkn and specific scenario 
- [ ] If it is a core feature, I have added thorough unit tests with above 80% coverage

*REQUIRED*:
Description of combination of tests performed and output of run

```bash
python run_kraken.py
...
<---insert test results output--->
```

OR


```bash
python -m coverage run -a -m unittest discover -s tests -v
...
<---insert test results output--->
```
