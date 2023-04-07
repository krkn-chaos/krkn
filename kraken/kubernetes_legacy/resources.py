from dataclasses import dataclass
from typing import List


@dataclass(frozen=True, order=False)
class Volume:
    """Data class to hold information regarding volumes in a pod"""
    name: str
    pvcName: str


@dataclass(order=False)
class VolumeMount:
    """Data class to hold information regarding volume mounts"""
    name: str
    mountPath: str


@dataclass(frozen=True, order=False)
class PVC:
    """Data class to hold information regarding persistent volume claims"""
    name: str
    capacity: str
    volumeName: str
    podNames: List[str]
    namespace: str


@dataclass(order=False)
class Container:
    """Data class to hold information regarding containers in a pod"""
    image: str
    name: str
    volumeMounts: List[VolumeMount]
    ready: bool = False


@dataclass(frozen=True, order=False)
class Pod:
    """Data class to hold information regarding a pod"""
    name: str
    podIP: str
    namespace: str
    containers: List[Container]
    nodeName: str
    volumes: List[Volume]


@dataclass(frozen=True, order=False)
class LitmusChaosObject:
    """Data class to hold information regarding a custom object of litmus project"""
    kind: str
    group: str
    namespace: str
    name: str
    plural: str
    version: str


@dataclass(frozen=True, order=False)
class ChaosEngine(LitmusChaosObject):
    """Data class to hold information regarding a ChaosEngine object"""
    engineStatus: str
    expStatus: str


@dataclass(frozen=True, order=False)
class ChaosResult(LitmusChaosObject):
    """Data class to hold information regarding a ChaosResult object"""
    verdict: str
    failStep: str



