from distutils.version import StrictVersion
from pathlib import Path
from typing import Optional, Collection, List, Dict, TextIO

from psij import Job, JobStatus, JobState
from psij.executors.batch.batch_scheduler_executor import BatchSchedulerExecutor, \
    BatchSchedulerExecutorConfig
from psij.executors.batch.script_generator import TemplatedScriptGenerator


class SlurmExecutorConfig(BatchSchedulerExecutorConfig):
    """A configuration class for the Slurm executor."""

    pass


class SlurmJobExecutor(BatchSchedulerExecutor):
    """A :proc:`~psij.JobExecutor` for the Slurm Workload Manager."""

    _NAME_ = 'slurm'
    _VERSION_ = StrictVersion('0.0.1')

    # see https://slurm.schedmd.com/squeue.html
    _STATE_MAP = {
        'BF': JobState.FAILED,
        'CA': JobState.CANCELED,
        'CD': JobState.COMPLETED,
        'CF': JobState.QUEUED,
        'CG': JobState.ACTIVE,
        'DL': JobState.FAILED,
        'F': JobState.FAILED,
        'NF': JobState.FAILED,
        'OOM': JobState.FAILED,
        'PD': JobState.QUEUED,
        'PR': JobState.FAILED,
        'R': JobState.ACTIVE,
        'RD': JobState.QUEUED,
        'RF': JobState.QUEUED,
        'RH': JobState.QUEUED,
        'RQ': JobState.ACTIVE,
        'SO': JobState.ACTIVE,
        'TO': JobState.FAILED,
        # TODO: double-check these
        'RS': JobState.ACTIVE,
        'RV': JobState.QUEUED,
        'SI': JobState.ACTIVE,
        'SE': JobState.ACTIVE,
        'ST': JobState.ACTIVE,
        'S': JobState.ACTIVE
    }

    # see https://slurm.schedmd.com/squeue.html
    _REASONS_MAP = {
        'AssociationJobLimit': 'The job\'s association has reached its maximum job count.',
        'AssociationResourceLimit': 'The job\'s association has reached some resource limit.',
        'AssociationTimeLimit': 'The job\'s association has reached its time limit.',
        'BadConstraints': 'The job\'s constraints can not be satisfied.',
        'BeginTime': 'The job\'s earliest start time has not yet been reached.',
        'Cleaning': 'The job is being requeued and still cleaning up from its previous execution.',
        'Dependency': 'This job is waiting for a dependent job to complete.',
        'FrontEndDown': 'No front end node is available to execute this job.',
        'InactiveLimit': 'The job reached the system InactiveLimit.',
        'InvalidAccount': 'The job\'s account is invalid.',
        'InvalidQOS': 'The job\'s QOS is invalid.',
        'JobHeldAdmin': 'The job is held by a system administrator.',
        'JobHeldUser': 'The job is held by the user.',
        'JobLaunchFailure': 'The job could not be launched.This may be due to a file system '
                            'problem, invalid program name, etc.',
        'Licenses': 'The job is waiting for a license.',
        'NodeDown': 'A node required by the job is down.',
        'NonZeroExitCode': 'The job terminated with a non-zero exit code.',
        'PartitionDown': 'The partition required by this job is in a DOWN state.',
        'PartitionInactive': 'The partition required by this job is in an Inactive state and not '
                             'able to start jobs.',
        'PartitionNodeLimit': 'The number of nodes required by this job is outside of its '
                              'partition\'s current limits. Can also indicate that required nodes '
                              'are DOWN or DRAINED.',
        'PartitionTimeLimit': 'The job\'s time limit exceeds its partition\'s current time limit.',
        'Priority': 'One or more higher priority jobs exist for this partition or advanced '
                    'reservation.',
        'Prolog': 'Its PrologSlurmctld program is still running.',
        'QOSJobLimit': 'The job\'s QOS has reached its maximum job count.',
        'QOSResourceLimit': 'The job\'s QOS has reached some resource limit.',
        'QOSTimeLimit': 'The job\'s QOS has reached its time limit.',
        'ReqNodeNotAvail': 'Some node specifically required by the job is not currently available. '
                           'The node may currently be in use, reserved for another job, in an '
                           'advanced reservation, DOWN, DRAINED, or not responding. Nodes which '
                           'are DOWN, DRAINED, or not responding will be identified as part of '
                           'the job\'s "reason" field as "UnavailableNodes". Such nodes will '
                           'typically require the intervention of a system administrator to make '
                           'available.',
        'Reservation': 'The job is waiting its advanced reservation to become available.',
        'Resources': 'The job is waiting for resources to become available.',
        'SystemFailure': 'Failure of the Slurm system, a file system, the network, etc.',
        'TimeLimit': 'The job exhausted its time limit.',
        'QOSUsageThreshold': 'Required QOS threshold has been breached.',
        'WaitingForScheduling': 'No reason has been set for this job yet. Waiting for the '
                                'scheduler to determine the appropriate reason.'
    }

    def __init__(self, url: Optional[str] = None, config: Optional[SlurmExecutorConfig] = None):
        """Initializes a :proc:`~SlurmJobExecutor`."""
        if not config:
            config = SlurmExecutorConfig()
        super().__init__(config=config)
        self.generator = TemplatedScriptGenerator(config, Path(__file__).parent / 'batch' / 'slurm'
                                                  / 'slurm.mustache')

    def generate_submit_script(self, job: Job, context: Dict[str, object],
                               submit_file: TextIO) -> None:
        self.generator.generate_submit_script(job, context, submit_file)

    def get_submit_command(self, job: Job, submit_file_path: Path) -> List[str]:
        """See :proc:`~BatchSchedulerExecutor.get_submit_command`."""
        return ['sbatch', str(submit_file_path.absolute())]

    def get_cancel_command(self, native_id: str) -> List[str]:
        """See :proc:`~BatchSchedulerExecutor.get_cancel_command`."""
        return ['scancel', native_id]

    def get_status_command(self, native_ids: Collection[str]) -> List[str]:
        """See :proc:`~BatchSchedulerExecutor.get_status_command`."""
        ids = ','.join(native_ids)

        # we're not really using job arrays, so this is equivalent to the job ID. However, if
        # we were to use arrays, this would return one ID for the entire array rather than
        # listing each element of the array independently
        return ['squeue', '-O', 'JobArrayID,StateCompact,Reason', '-t', 'all', '-j', ids]

    def parse_status_output(self, out: str) -> Dict[str, JobStatus]:
        """See :proc:`~BatchSchedulerExecutor.parse_status_output`."""
        r = {}
        lines = iter(out.split('\\n'))
        # skip header
        lines.__next__()
        for line in lines:
            cols = line.split()
            assert len(cols) == 3
            native_id = cols[0]
            state = self._get_state(cols[1])
            msg = self._get_message(cols[2]) if state == JobState.FAILED else None
            r[native_id] = JobStatus(state, message=msg)

        return r

    def _get_state(self, state: str) -> JobState:
        assert state in SlurmJobExecutor._STATE_MAP
        return SlurmJobExecutor._STATE_MAP[state]

    def _get_message(self, reason: str) -> str:
        assert reason in SlurmJobExecutor._REASONS_MAP
        return SlurmJobExecutor._REASONS_MAP[reason]

    def job_id_from_submit_output(self, out: str) -> str:
        """See :proc:`~BatchSchedulerExecutor.job_id_from_submit_output`."""
        return out.strip().split()[-1]


__PSI_J_EXECUTORS__ = [SlurmJobExecutor]
