### Signaling to Kraken
This functionality allows a user to be able to pause or stop the kraken run at any time no matter the number of iterations or daemon_mode set in the config.

If publish_kraken_status is set to True in the config, kraken will start up a connection to a url at a certain port to decide if it should continue running.

By default, it will get posted to http://0.0.0.0:8081/

An example use case for this feature would be coordinating kraken runs based on the status of the service installation or load on the cluster.



#### States
There are 3 states in the kraken status:

```PAUSE```: When the Kraken signal is 'PAUSE', this will pause the kraken test and wait for the wait_duration until the signal returns to RUN.

```STOP```: When the Kraken signal is 'STOP', end the kraken run and print out report.

```RUN```: When the Kraken signal is 'RUN', continue kraken run based on iterations.



#### Cleanup During Unexpected Failures

When Krkn is interrupted (Ctrl+C) or killed unexpectedly, it will automatically:

1. Capture current state artifacts:
   - Logs from the last 5 minutes
   - Cluster events (if enabled)
   - Current scenario state
   - Resource status

2. Run scenario-specific cleanup:
   - Each scenario plugin implements its own cleanup method
   - Resources are restored to their original state
   - Temporary resources are removed
   - Network policies are cleaned up

3. Save cleanup status:
   - Timestamp of cleanup
   - Scenario being cleaned up
   - Cleanup success/failure status
   - Saved to cleanup_status.json

4. Exit gracefully:
   - All cleanup operations complete
   - Status is saved
   - Process exits with status 0



#### Configuration

In the config you need to set these parameters to tell kraken which port to post the kraken run status to.
As well if you want to publish and stop running based on the kraken status or not.
The signal is set to `RUN` by default, meaning it will continue to run the scenarios. It can set to `PAUSE` for Kraken to act as listener and wait until set to `RUN` before injecting chaos.
```
    port: 8081
    publish_kraken_status: True
    signal_state: RUN
```


#### Setting Signal

You can reset the kraken status during kraken execution with a `set_stop_signal.py` script with the following contents:

```
import http.client as cli

conn = cli.HTTPConnection("0.0.0.0", "<port>")

conn.request("POST", "/STOP", {})

# conn.request('POST', '/PAUSE', {})

# conn.request('POST', '/RUN', {})

response = conn.getresponse()
print(response.read().decode())
```

Make sure to set the correct port number in your set_stop_signal script.

##### Url Examples
To stop run:

```
curl -X POST http:/0.0.0.0:8081/STOP
```

To pause run:
```
curl -X POST http:/0.0.0.0:8081/PAUSE
```

To start running again:
```
curl -X POST http:/0.0.0.0:8081/RUN
```
