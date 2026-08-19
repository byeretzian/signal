from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from signal_app.agent import GrowthAgent, RuleBasedQuestionInterpreter
from signal_app.models import Artist, ArtistMetricSnapshot


def test_growth_question_executes_deterministic_tool(session: Session) -> None:
    artist = Artist(name="Kelly Lee Owens")
    session.add(artist)
    session.flush()
    session.add_all(
        [
            ArtistMetricSnapshot(
                artist_id=artist.id,
                snapshot_date=date(2026, 3, 1),
                source="test",
                listener_count=200,
            ),
            ArtistMetricSnapshot(
                artist_id=artist.id,
                snapshot_date=date(2026, 3, 31),
                source="test",
                listener_count=230,
            ),
        ]
    )
    session.commit()

    result = GrowthAgent(session=session, interpreter=RuleBasedQuestionInterpreter()).run(
        question="How much has this artist grown over the last 30 days?",
        artist_id=artist.id,
        artist_name=artist.name,
        end_date=date(2026, 3, 31),
        source="test",
    )

    assert result.supporting_data is not None
    assert result.supporting_data.percentage_change == 15.0
    assert [tool.tool for tool in result.tools] == ["calculate_growth"]
    assert result.tools[0].success is True


def test_unsupported_question_does_not_claim_tool_execution(session: Session) -> None:
    artist = Artist(name="Test Artist")
    session.add(artist)
    session.commit()

    result = GrowthAgent(session=session, interpreter=RuleBasedQuestionInterpreter()).run(
        question="What label released the debut album?",
        artist_id=artist.id,
        artist_name=artist.name,
        end_date=date(2026, 3, 31),
        source="test",
    )

    assert result.tools == []
    assert result.supporting_data is None
