"""
workflow_fetcher.py — Fetches real AI tool workflows and use cases.

Sources that work from Railway (no IP blocking):
- HackerNews API (show HN + Ask HN AI posts)
- Product Hunt AI feed
- DEV.to AI tag RSS
- Hashnode AI tag
- Curated rotating topics (50+ unique topics)
"""

import requests
import feedparser
import random
from bs4 import BeautifulSoup
from utils.logger import get_logger

logger = get_logger("workflow_fetcher")


def _fetch_hackernews_ai() -> list[dict]:
    """Fetch AI-related posts from HackerNews API — always works from servers."""
    ideas = []
    try:
        # Get top stories
        resp = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            timeout=8,
        )
        story_ids = resp.json()[:80]  # check top 80

        AI_KEYWORDS = [
            "ai", "llm", "gpt", "claude", "gemini", "chatgpt", "openai",
            "anthropic", "ollama", "stable diffusion", "midjourney",
            "automation", "agent", "workflow", "prompt", "free tool",
            "ml", "machine learning", "deep learning", "copilot",
        ]

        count = 0
        for sid in story_ids:
            if count >= 4:
                break
            try:
                story = requests.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                    timeout=5,
                ).json()
                title = story.get("title", "").lower()
                if any(kw in title for kw in AI_KEYWORDS):
                    ideas.append({
                        "title": story.get("title", ""),
                        "summary": f"HN discussion with {story.get('score', 0)} points, {story.get('descendants', 0)} comments",
                        "source": "HackerNews",
                        "url": story.get("url", f"https://news.ycombinator.com/item?id={sid}"),
                    })
                    count += 1
            except Exception:
                continue

        logger.info(f"[HackerNews]: found {count} AI ideas")
    except Exception as e:
        logger.warning(f"[HackerNews] failed: {e}")
    return ideas


def _fetch_devto_ai() -> list[dict]:
    """Fetch AI tutorials from DEV.to — open API, no auth needed."""
    ideas = []
    try:
        resp = requests.get(
            "https://dev.to/api/articles?tag=ai&per_page=6&top=7",
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        articles = resp.json()
        for a in articles[:4]:
            title = a.get("title", "")
            if not title:
                continue
            ideas.append({
                "title": title,
                "summary": a.get("description", "")[:300],
                "source": "DEV.to",
                "url": a.get("url", ""),
            })
        logger.info(f"[DEV.to AI]: found {len(ideas)} ideas")
    except Exception as e:
        logger.warning(f"[DEV.to] failed: {e}")
    return ideas


def _fetch_producthunt_ai() -> list[dict]:
    """Fetch AI tools from Product Hunt RSS."""
    ideas = []
    try:
        feed = feedparser.parse("https://www.producthunt.com/feed?category=artificial-intelligence")
        for entry in feed.entries[:4]:
            title = entry.get("title", "")
            if not title:
                continue
            summary = ""
            if hasattr(entry, "summary"):
                soup = BeautifulSoup(entry.summary, "html.parser")
                summary = soup.get_text()[:300].strip()
            ideas.append({
                "title": title,
                "summary": summary,
                "source": "Product Hunt",
                "url": entry.get("link", ""),
            })
        logger.info(f"[Product Hunt AI]: found {len(ideas)} ideas")
    except Exception as e:
        logger.warning(f"[Product Hunt] failed: {e}")
    return ideas


# 50+ curated topics — rotated randomly so posts never repeat
CURATED_TOPICS = [
    # Free tool replacements
    ("Use Claude free to replace Grammarly ($20/month)", "Claude rewrites, proofreads and improves writing better than Grammarly — completely free on Claude.ai"),
    ("Use Perplexity free to replace Google Scholar", "Perplexity cites real sources and gives research-level answers — free tier is very generous"),
    ("Use ChatGPT free to replace an Excel consultant", "Describe what you want in plain English, get the exact formula or VBA macro instantly"),
    ("Use NotebookLM free to replace a research assistant", "Google's NotebookLM reads your PDFs and lets you ask questions about them — free"),
    ("Use Gamma free to replace PowerPoint designers", "Gamma generates beautiful slide decks from a prompt in seconds — no design skills needed"),
    ("Use Claude free to replace a copywriter", "Claude writes landing pages, emails, ads and product descriptions better than most freelancers"),
    ("Use Suno free to replace background music subscriptions", "Suno generates original music from text descriptions — free tier gives 50 songs/day"),
    ("Use Udio free to replace stock music sites", "Udio creates royalty-free music from a simple prompt — completely free to start"),
    ("Use Runway free to replace video editors", "Runway's free tier does AI video editing, background removal and motion tracking"),
    ("Use ElevenLabs free to replace voiceover artists", "ElevenLabs free tier gives you 10,000 characters/month of professional AI voice"),
    # Career uses
    ("Use Claude to prepare for any job interview in 30 min", "Paste the job description, Claude generates likely questions and perfect answers tailored to you"),
    ("Use ChatGPT to write a resume that beats ATS filters", "Most resumes get rejected by AI before a human sees them. ChatGPT knows exactly how to format yours"),
    ("Use AI to negotiate a higher salary", "Claude can role-play salary negotiations and give you the exact scripts that work"),
    ("Use ChatGPT to write cold emails that get replies", "Most cold emails get ignored. Here's the exact prompt to write ones that get 30%+ reply rates"),
    ("Use Claude to turn your LinkedIn into a job magnet", "A Claude-optimized LinkedIn profile gets 3x more recruiter messages"),
    # Productivity hacks
    ("Use ChatGPT to summarize any YouTube video in 30 sec", "Paste the transcript URL and get a full summary with key takeaways instantly"),
    ("Use Claude to write a week of social posts in 10 min", "One prompt generates 7 days of varied, platform-specific content ready to schedule"),
    ("Use AI to automate your morning news briefing", "Set up a free automation that summarizes top news in your niche and emails it to you daily"),
    ("Use ChatGPT to turn meeting notes into action items", "Paste messy meeting notes, get a clean summary with owner and deadline for every action"),
    ("Use Claude to write your performance review", "Most people undersell themselves. Claude writes bullet points that make your work impossible to ignore"),
    # Business uses
    ("Use ChatGPT to build a $0 business plan", "A complete business plan with market analysis, financial projections and launch strategy — from one prompt"),
    ("Use Claude to write product descriptions that sell", "Claude writes product copy that converts better than most professional copywriters for free"),
    ("Use AI to create a customer service script", "Claude generates full customer service playbooks covering every common scenario in minutes"),
    ("Use ChatGPT to analyze competitor websites", "Paste a competitor's homepage text and get a full SWOT analysis and gap opportunities"),
    ("Use Claude to write Terms of Service for free", "Most startups pay lawyers $500+ for this. Claude writes legally sound ToS in minutes"),
    # Technical
    ("Use Claude to debug code 10x faster", "Paste your error and code, Claude not only fixes it but explains WHY it broke"),
    ("Use ChatGPT to learn any programming language in a week", "ChatGPT creates a personalized learning plan with daily exercises based on your current level"),
    ("Use AI to write SQL queries without knowing SQL", "Describe your data question in plain English, get the exact SQL query that runs immediately"),
    ("Use Claude to review your code for security issues", "Claude spots vulnerabilities that most developers miss — SQL injection, XSS, authentication flaws"),
    ("Use ChatGPT to generate unit tests automatically", "Paste your function, get complete test coverage with edge cases in seconds"),
    # Content creation
    ("Use Claude to write a viral Twitter thread", "The exact prompt framework that generates threads getting 1000+ retweets on AI topics"),
    ("Use ChatGPT to repurpose one blog post into 10 pieces", "One article becomes tweets, LinkedIn posts, email newsletter, YouTube script and more"),
    ("Use AI to generate 30 days of Instagram captions", "One prompt gives you a full month of captions with hooks, hashtags and CTAs"),
    ("Use Claude to write YouTube video scripts", "Claude writes engaging scripts with hooks, story arcs and CTAs optimized for retention"),
    ("Use AI to write a book outline in one hour", "From zero to a full non-fiction book structure with chapter summaries — completely free"),
    # Finance
    ("Use ChatGPT to track and analyze your spending", "Paste your bank statement, get a breakdown of spending patterns and saving opportunities"),
    ("Use Claude to write grant proposals for free", "Grant writing usually costs $2000+. Claude writes compelling proposals that match funder criteria"),
    ("Use AI to understand any legal contract", "Paste any contract, Claude explains every clause in plain English and flags risky terms"),
    ("Use ChatGPT to build a personal budget template", "Describe your income and goals, get a complete personalized budget spreadsheet formula"),
    # Health/Learning
    ("Use Claude to create a personalized study plan", "Paste your syllabus, Claude builds a day-by-day study schedule optimized for retention"),
    ("Use ChatGPT to explain any medical report", "Paste your lab results, get a clear plain-English explanation of every value and what it means"),
    ("Use AI to learn any skill 3x faster", "Claude creates spaced repetition flashcards and practice exercises for any topic you want to master"),
    ("Use Perplexity to fact-check anything instantly", "Before sharing news, paste it into Perplexity — it verifies facts and shows original sources"),
]


def fetch_workflow_ideas(max_results: int = 10) -> list[dict]:
    """
    Fetch real AI workflow ideas from live sources + curated rotating topics.
    Returns list of {title, summary, source, url}
    """
    live_ideas = []

    # Fetch from live sources that work from Railway
    live_ideas.extend(_fetch_hackernews_ai())
    live_ideas.extend(_fetch_devto_ai())
    live_ideas.extend(_fetch_producthunt_ai())

    # Pick random curated topics (shuffled so they rotate each run)
    shuffled_curated = random.sample(CURATED_TOPICS, min(len(CURATED_TOPICS), 15))
    curated_ideas = [
        {"title": t, "summary": s, "source": "curated", "url": ""}
        for t, s in shuffled_curated
    ]

    # Mix live + curated (live ideas first so they get priority)
    all_ideas = live_ideas + curated_ideas

    logger.info(f"Total workflow ideas: {len(all_ideas)} ({len(live_ideas)} live, {len(curated_ideas)} curated)")
    return all_ideas[:max_results]
