import time
from gpt_researcher.config import Config
from gpt_researcher.master.functions import *
from gpt_researcher.context.compression import ContextCompressor
from gpt_researcher.memory import Memory


class GPTResearcher:
    """
    GPT Researcher
    """
    def __init__(self, query, report_type, source_urls=None, config_path=None, websocket=None):
        """
        Initialize the GPT Researcher class.
        Args:
            query:
            report_type:
            config_path:
            websocket:
        """
        self.query = query
        self.agent = None
        self.role = None
        self.report_type = report_type
        self.websocket = websocket
        self.cfg = Config(config_path)
        self.retriever = get_retriever(self.cfg.retriever)
        self.context = []
        self.source_urls = source_urls
        self.memory = Memory()
        self.visited_urls = set()

    async def run(self):
        """
        Runs the GPT Researcher
        Returns:
            Report
        """
        print(f"🔎 Running research for '{self.query}'...")
        # Generate Agent
        self.agent, self.role = await choose_agent(self.query, self.cfg)
        await stream_output("logs", self.agent, self.websocket)

        # If specified, the researcher will use the given urls as the context for the research.
        if self.source_urls:
            self.context = await self.get_context_by_urls(self.source_urls)
        else:
            self.context = await self.get_context_by_search(self.query)

        # Write Research Report
        if self.report_type == "custom_report":
            self.role = self.cfg.agent_role if self.cfg.agent_role else self.role
        await stream_output("logs", f"✍️ Writing {self.report_type} for research task: {self.query}...", self.websocket)
        report = await generate_report(query=self.query, context=self.context,
                                       agent_role_prompt=self.role, report_type=self.report_type,
                                       websocket=self.websocket, cfg=self.cfg)
        time.sleep(2)
        return report

    async def get_context_by_urls(self, urls):
        """
            Scrapes and compresses the context from the given urls
        """
        new_search_urls = await self.get_new_urls(urls)
        await stream_output("logs",
                            f"🧠 I will conduct my research based on the following urls: {new_search_urls}...",
                            self.websocket)
        scraped_sites = scrape_urls(new_search_urls, self.cfg)
        return await self.get_similar_content_by_query(self.query, scraped_sites)

    async def get_context_by_search(self, query):
        """
           Generates the context for the research task by searching the query and scraping the results
        Returns:
            context: List of context
        """
        context = []
        # Generate Sub-Queries including original query
        sub_queries = await get_sub_queries(query, self.role, self.cfg) + [query]
        await stream_output("logs",
                            f"🧠 다음과 같은 검색어로 정보를 검색 : {sub_queries}...",
                            self.websocket)

        # Run Sub-Queries
        for sub_query in sub_queries:
            await stream_output("logs", f"\n🔎 Running research for '{sub_query}'...", self.websocket)
            scraped_sites = await self.scrape_sites_by_query(sub_query)
            content = await self.get_similar_content_by_query(sub_query, scraped_sites)
            await stream_output("logs", f"📃 {content}", self.websocket)
            context.append(content)

        return context

    async def get_new_urls(self, url_set_input):
        """ Gets the new urls from the given url set.
        Args: url_set_input (set[str]): The url set to get the new urls from
        Returns: list[str]: The new urls from the given url set
        """

        new_urls = []
        for url in url_set_input:
            if url not in self.visited_urls:
                await stream_output("logs", f"✅ Adding source url to research: {url}\n", self.websocket)

                self.visited_urls.add(url)
                new_urls.append(url)

        return new_urls

    # TODO: 이 함수는 검색을 해서 여러 기사들과 문서들 정보를 제공하고 있지만, embedding 거리가 가까운 문서들을 취합하여, 파싱하는 작업을 수행해야 함
    async def scrape_sites_by_query(self, sub_query):
        """
        Runs a sub-query
        Args:
            sub_query:

        Returns:
            Summary
        """
        # Get Urls
        retriever = self.retriever(sub_query)
        search_results = retriever.search(max_results=self.cfg.max_search_results_per_query)
        new_search_urls = await self.get_new_urls([url.get("href") for url in search_results])

        # Scrape Urls
        # await stream_output("logs", f"📝Scraping urls {new_search_urls}...\n", self.websocket)
        await stream_output("logs", f"🤔Researching for relevant information...\n", self.websocket)
        scraped_content_results = scrape_urls(new_search_urls, self.cfg)
        return scraped_content_results

    #TODO: 이 함수는 query에 관련된 여러 웹사이트 데이터 리스트를 가져와서 하나의 문서로 만드는 함수. 우리 문서로 여러 문서를 취합해야 할경우 비슷한 로직이 필요
    async def get_similar_content_by_query(self, query, pages):
        await stream_output("logs", f"📃 Getting relevant content based on query: {query}...", self.websocket)
        # Summarize Raw Data
        context_compressor = ContextCompressor(documents=pages, embeddings=self.memory.get_embeddings())
        # Run Tasks
        return context_compressor.get_context(query, max_results=8)

