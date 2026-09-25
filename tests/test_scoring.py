from datetime import date

import pytest

from jobagg.config import ScoringConfig
from jobagg.models import Job, RemoteType
from jobagg.scoring import NoopRelevance, Scorer, load_relevance_checker

TODAY = date(2026, 9, 25)


def _job(title="Frontend Developer", **kw) -> Job:
    base = dict(source="x", source_url=f"https://x/{title}", company="ACME", title=title)
    base.update(kw)
    return Job(**base)


@pytest.fixture
def scorer() -> Scorer:
    cfg = ScoringConfig(stack_tags={"vue": 1.0, "nuxt": 1.0, "typescript": 0.7, "react": 0.3})
    return Scorer(cfg, max_age_days=14)


def test_best_case_scores_100(scorer):
    job = _job("Senior Vue Developer", remote_type=RemoteType.REMOTE, salary_min=100000,
               posted_at=TODAY, tech_tags=["vue", "nuxt", "typescript"])
    scorer.score(job, TODAY)
    assert job.score == 100.0
    assert job.score_breakdown == {"stack": 45.0, "remote": 25.0, "seniority": 15.0,
                                   "salary": 5.0, "freshness": 10.0}


def test_stack_component_prefers_title_and_caps_at_one(scorer):
    assert scorer.stack(_job("Vue Developer")) == 1.0
    assert scorer.stack(_job("Frontend Developer", tech_tags=["typescript"])) == pytest.approx(
        0.7 / 1.5)
    assert scorer.stack(_job("Frontend Developer", tech_tags=["vue", "nuxt"])) == 1.0
    assert scorer.stack(_job("Backend Developer")) == 0.0


def test_remote_ranking(scorer):
    order = [RemoteType.REMOTE, RemoteType.HYBRID, RemoteType.UNKNOWN, RemoteType.ONSITE]
    values = [scorer.remote(_job(remote_type=r)) for r in order]
    assert values == sorted(values, reverse=True)


def test_seniority(scorer):
    assert scorer.seniority(_job("Senior Vue Developer")) == 1.0
    assert scorer.seniority(_job("Vue Developer")) == 0.6
    assert scorer.seniority(_job("Frontend Lead")) == 0.3
    assert scorer.seniority(_job("Senior Lead Engineer")) == 1.0
    assert scorer.seniority(_job("Junior Vue Developer")) == 0.0


def test_freshness_decays(scorer):
    assert scorer.freshness(_job(posted_at=TODAY), TODAY) == 1.0
    assert scorer.freshness(_job(posted_at=date(2026, 9, 22)), TODAY) == 1.0
    mid = scorer.freshness(_job(posted_at=date(2026, 9, 15)), TODAY)
    assert 0.0 < mid < 1.0
    assert scorer.freshness(_job(posted_at=date(2026, 9, 1)), TODAY) == 0.0
    assert scorer.freshness(_job(posted_at=None), TODAY) == 0.5


def test_ordering_matches_profile(scorer):
    remote_vue = _job("Vue Developer", remote_type=RemoteType.REMOTE, posted_at=TODAY)
    onsite_vue = _job("Vue Developer", remote_type=RemoteType.ONSITE, posted_at=TODAY)
    remote_react = _job("React Developer", remote_type=RemoteType.REMOTE, posted_at=TODAY,
                        tech_tags=["react"])
    scores = [j.score for j in scorer.score_all([remote_vue, onsite_vue, remote_react], TODAY)]
    assert scores[0] > scores[1] and scores[0] > scores[2]


class DoubleRelevance:
    def adjust(self, job: Job, score: float) -> float:
        return score + 10


def test_relevance_extension_point():
    assert isinstance(load_relevance_checker("none"), NoopRelevance)
    checker = load_relevance_checker("tests.test_scoring:DoubleRelevance")
    scorer = Scorer(ScoringConfig(), relevance=checker)
    job = scorer.score(_job("Vue Developer", posted_at=TODAY), TODAY)
    assert job.score_breakdown["relevance"] == 10.0
    with pytest.raises(ValueError):
        load_relevance_checker("no-colon")
