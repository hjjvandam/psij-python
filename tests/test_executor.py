from pathlib import Path
from psij import SubmitException, Job, JobExecutor, JobSpec, JobState
from tempfile import TemporaryDirectory

from executor_test_params import ExecutorTestParams


def assert_completed(job: Job) -> None:
    if job.status.state == JobState.FAILED:
        raise RuntimeError('Job (native_id: {}) failed: {}'.format(job.native_id,
                                                                   job.status.message))
    elif job.status.state == JobState.COMPLETED:
        return
    else:
        raise RuntimeError('Unexpected job state: {}'.format(job.status.state))


def _get_executor_instance(ep: ExecutorTestParams, job: Job) -> JobExecutor:
    assert job.spec is not None
    job.spec.launcher = ep.launcher
    return JobExecutor.get_instance(ep.executor, url=ep.url)


def test_simple_job(execparams: ExecutorTestParams) -> None:
    job = Job(JobSpec(executable='/bin/date', launcher=execparams.launcher))
    ex = _get_executor_instance(execparams, job)
    ex.submit(job)
    job.wait()


def test_simple_job_redirect(execparams: ExecutorTestParams) -> None:
    with TemporaryDirectory(dir=Path.home() / '.psij' / 'work') as td:
        outp = Path(td, 'stdout.txt')
        job = Job(JobSpec(executable='/bin/echo', arguments=['-n', '_x_'], stdout_path=outp))
        ex = _get_executor_instance(execparams, job)
        ex.submit(job)
        job.wait()
        f = outp.open("r")
        contents = f.read()
        assert contents == '_x_'


def test_attach(execparams: ExecutorTestParams) -> None:
    job = Job(JobSpec(executable='/bin/sleep', arguments=['1']))
    ex = _get_executor_instance(execparams, job)
    ex.submit(job)
    job.wait(target_states=[JobState.ACTIVE, JobState.COMPLETED])
    native_id = job.native_id

    assert native_id is not None
    job2 = Job()
    ex.attach(job2, native_id)
    job2.wait()


def test_cancel(execparams: ExecutorTestParams) -> None:
    job = Job(JobSpec(executable='/bin/sleep', arguments=['60']))
    ex = _get_executor_instance(execparams, job)
    ex.submit(job)
    job.wait(target_states=[JobState.ACTIVE])
    job.cancel()
    status = job.wait()
    assert status is not None
    assert status.state == JobState.CANCELED


def test_failing_job(execparams: ExecutorTestParams) -> None:
    job = Job(JobSpec(executable='/bin/false'))
    ex = _get_executor_instance(execparams, job)
    ex.submit(job)
    status = job.wait()
    assert status is not None
    assert status.state == JobState.FAILED
    assert status.exit_code is not None
    assert status.exit_code != 0


def test_missing_executable(execparams: ExecutorTestParams) -> None:
    job = Job(JobSpec(executable='/bin/no_such_file_or_directory'))
    ex = _get_executor_instance(execparams, job)
    # we don't know if this will fail with an exception or JobState.FAILED,
    # so handle both
    try:
        ex.submit(job)
        status = job.wait()
        assert status is not None
        assert status.state == JobState.FAILED
        assert status.exit_code is not None
        assert status.exit_code != 0
    except SubmitException:
        pass


def test_parallel_jobs(execparams: ExecutorTestParams) -> None:
    spec = JobSpec(executable='/bin/sleep', arguments=['5'])
    job1 = Job(spec)
    job2 = Job(spec)
    ex = _get_executor_instance(execparams, job1)
    ex.submit(job1)
    ex.submit(job2)
    job1.wait()
    job2.wait()
    assert_completed(job1)
    assert_completed(job2)