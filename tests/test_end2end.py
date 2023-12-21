import pytest

from gpt_researcher import GPTResearcher


class TestEnd2End:
    @pytest.mark.asyncio
    async def test_end2end(self):
        # Query
        query = "내년에 석유값이 어떻게 될까요?"

        # Report Type
        report_type = "research_report"

        # Run Research
        researcher = GPTResearcher(query=query, report_type=report_type, config_path=None)
        report = await researcher.run()
        return report