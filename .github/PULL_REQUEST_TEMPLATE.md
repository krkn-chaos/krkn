# Type of change

- [ ] Refactor
- [ ] New feature
- [ ] Bug fix
- [ ] Optimization

# Description  
<-- Provide a brief description of the changes made in this PR. -->  

## Related Tickets & Documents
If no related issue, please create one and start the converasation on wants of 

- Related Issue #: 
- Closes #: 

# Documentation  
- [ ] **Is documentation needed for this update?**

If checked, a documentation PR must be created and merged in the [website repository](https://github.com/krkn-chaos/website/).

## Related Documentation PR (if applicable)  
<-- Add the link to the corresponding documentation PR in the website repository -->  

# Checklist before requesting a review
[ ] Ensure the changes and proposed solution have been discussed in the relevant issue and have received acknowledgment from the community or maintainers. See [contributing guidelines](https://krkn-chaos.dev/docs/contribution-guidelines/)
See [testing your changes](https://krkn-chaos.dev/docs/developers-guide/testing-changes/) and run on any Kubernetes or OpenShift cluster to validate your changes
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
