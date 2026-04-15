"""
content_writer.py — Uses Claude (Anthropic) to generate platform-specific posts
from the latest AI news. Produces 3 post types daily:
  1. AI Daily Brief  (EOD anchor)
  2. Learning Post   (teach 1 AI skill in 60s)
  3. Differentiator  (opinion / impact / viral curiosity)

Each post is formatted for X, LinkedIn, and Instagram.
"""

import json
import os
import anthropic
from dataclasses import dataclass
from datetime import datetime
from utils.logger import get_logger

STRATEGY_FILE = os.path.join(os.path.dirname(__file__), "..", "logs", "content_strategy.json")


def _load_posted_topics() -> list[str]:
    """Load list of already-posted topics to avoid duplicates."""
    try:
        from utils.redis_store import get_posted_topics
        return get_posted_topics()
    except Exception:
        return []


def _save_posted_topic(topic: str):
    """Save a posted topic to Redis."""
    try:
        from utils.redis_store import save_posted_topic
        save_posted_topic(topic)
    except Exception:
        pass

logger = get_logger("content_writer")

SYSTEM_PROMPT = """You are an expert AI content strategist for a brand called {brand_name}.

Brand Mission: {brand_niche}
Tone: {brand_tone}
Core message: "Use AI or fall behind in your career."

You write 3 types of posts:

1. AI DAILY BRIEF — EOD anchor post
   Hook: Strong headline
   Body: What happened (1-2 lines) + Why it matters for careers
   CTA: Follow for daily AI updates

2. LEARNING POST — Teach 1 AI skill in 60 seconds
   Hook: "Learn [X] in 60 seconds"
   Body: 1 concept → 1 real use case → 1 action step
   CTA: Save this post

3. DIFFERENTIATOR — Bold opinion/impact/viral
   Hook: Controversial or curiosity-driven
   Body: Strong take + proof
   CTA: Comment your thoughts

RULES:
- No fluff. Every word must earn its place.
- Career impact must be explicit (money, time, job security)
- Hooks must stop the scroll
- Always return valid JSON only — no markdown, no extra text.
"""

PLATFORM_SPECS = {
    "twitter": {
        "max_chars": 280,
        "style": "punchy, 1-3 lines, hook must be first line, use thread format for longer posts (1/n)",
        "hashtags": 2,
    },
    "linkedin": {
        "max_chars": 3000,
        "style": "professional but sharp, line breaks after every sentence, no walls of text, emoji OK",
        "hashtags": 5,
    },
    "instagram": {
        "max_chars": 2200,
        "style": "visual-first caption, punchy opener, bullet points, strong CTA, emojis encouraged",
        "hashtags": 15,
    },
}


@dataclass
class GeneratedPost:
    post_type: str          # daily_brief | learning | differentiator
    topic: str
    twitter_text: str
    linkedin_text: str
    instagram_caption: str
    instagram_hashtags: str
    image_prompt: str       # prompt for Canva/image generation
    key_message: str        # 1-line summary for image headline
    reel_script: str        # 15-25 second voiceover script for Reels


def _load_strategy() -> dict:
    """Load analyst-optimized content strategy if available."""
    if os.path.exists(STRATEGY_FILE):
        try:
            with open(STRATEGY_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


class ContentWriter:
    def __init__(self, api_key: str, brand_name: str, brand_niche: str, brand_tone: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.brand_name = brand_name
        self.brand_niche = brand_niche
        self.brand_tone = brand_tone

        # Load analyst strategy and inject into system prompt
        strategy = _load_strategy()
        strategy_notes = ""
        if strategy:
            strategy_notes = f"""
PERFORMANCE-OPTIMIZED STRATEGY (learned from engagement data):
- Top performing topics: {', '.join(strategy.get('top_topics', []))}
- Best hooks: {', '.join(strategy.get('best_hooks', []))}
- Avoid: {', '.join(strategy.get('avoid_topics', []))}
- Best post type: {strategy.get('best_post_type', '')}
- Tone notes: {strategy.get('tone_notes', '')}
- Hashtag notes: {strategy.get('hashtag_notes', '')}

Apply these learnings to maximize engagement.
"""
            logger.info("Content strategy loaded from Analyst Agent.")

        self.system = SYSTEM_PROMPT.format(
            brand_name=brand_name,
            brand_niche=brand_niche,
            brand_tone=brand_tone,
        ) + strategy_notes

    def _call_claude(self, prompt: str) -> str:
        """Call Claude with streaming and return full text response."""
        full_text = ""
        with self.client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=self.system,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                full_text += text
        return full_text.strip()

    def _parse_json(self, raw: str) -> dict:
        """Extract and parse JSON from Claude's response."""
        # Strip markdown code fences if present
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        return json.loads(raw.strip())

    def write_daily_brief(self, articles: list[dict]) -> GeneratedPost:
        """Generate the AI Daily Brief post from today's top news."""
        posted = _load_posted_topics()
        posted_str = ", ".join(posted[-10:]) if posted else "none"

        headlines = "\n".join(
            f"- [{a['source']}] {a['title']}: {a['summary'][:150]}"
            for a in articles[:8]
        )

        prompt = f"""Today's top AI news headlines:
{headlines}

Already posted about these topics recently (DO NOT repeat these): {posted_str}

Write an AI DAILY BRIEF post. Pick a DIFFERENT story from the already-posted list.
Must be the most career-relevant story not yet covered.

Return ONLY this JSON (no markdown, no extra text):
{{
  "topic": "one-line topic name",
  "key_message": "one punchy headline for the image (max 5 words, ALL CAPS, punchy)",
  "image_prompt": "describe a simple branded image for this post (no text in image, just visual concept)",
  "twitter_text": "tweet version (max 280 chars, strong hook first line)",
  "linkedin_text": "linkedin version (professional, line breaks, 150-300 words)",
  "instagram_caption": "instagram caption (punchy opener, bullets, CTA)",
  "instagram_hashtags": "15 relevant hashtags as a single string starting with space",
  "reel_script": "15-20 second spoken script for a news anchor voiceover. Start with a hook, deliver the key fact, explain why it matters for careers. Conversational, no hashtags, no emojis. Max 60 words."
}}"""

        raw = self._call_claude(prompt)
        data = self._parse_json(raw)
        _save_posted_topic(data.get("topic", ""))
        logger.info(f"Daily Brief generated: {data.get('topic', '')}")

        return GeneratedPost(
            post_type="daily_brief",
            topic=data["topic"],
            twitter_text=data["twitter_text"],
            linkedin_text=data["linkedin_text"],
            instagram_caption=data["instagram_caption"],
            instagram_hashtags=data["instagram_hashtags"],
            image_prompt=data["image_prompt"],
            key_message=data["key_message"],
            reel_script=data.get("reel_script", ""),
        )

    def write_learning_post(self, articles: list[dict]) -> GeneratedPost:
        """Generate a Learning Post — teach 1 AI skill in 60 seconds."""
        context = "\n".join(
            f"- {a['title']}"
            for a in articles[:8]
        )

        prompt = f"""Recent AI news context:
{context}

Write a LEARNING POST that teaches one practical AI skill in 60 seconds.
Pick a skill from the news context that helps people in their careers.

Return ONLY this JSON (no markdown, no extra text):
{{
  "topic": "skill name",
  "key_message": "Learn [X] in 60 seconds (max 5 words, ALL CAPS, punchy)",
  "image_prompt": "describe a clean visual concept for a learning post image (no text overlay needed)",
  "twitter_text": "tweet thread version: tweet 1/3 hook + 2/3 concept + 3/3 action (max 280 chars each, format as thread)",
  "linkedin_text": "linkedin version with hook, concept explanation, real use case, action step (150-250 words)",
  "instagram_caption": "instagram carousel caption: hook + 3-4 bullet slides description + save CTA",
  "instagram_hashtags": "15 relevant hashtags as a single string starting with space",
  "reel_script": "15-20 second spoken script teaching this skill. Start with a hook, explain concept in simple terms, give one action step. Conversational, no hashtags, max 60 words."
}}"""

        raw = self._call_claude(prompt)
        data = self._parse_json(raw)
        _save_posted_topic(data.get("topic", ""))
        logger.info(f"Learning Post generated: {data.get('topic', '')}")

        return GeneratedPost(
            post_type="learning",
            topic=data["topic"],
            twitter_text=data["twitter_text"],
            linkedin_text=data["linkedin_text"],
            instagram_caption=data["instagram_caption"],
            instagram_hashtags=data["instagram_hashtags"],
            image_prompt=data["image_prompt"],
            key_message=data["key_message"],
            reel_script=data.get("reel_script", ""),
        )

    def write_differentiator_post(self, articles: list[dict]) -> GeneratedPost:
        """Generate a Differentiator post — bold opinion or viral take."""
        context = "\n".join(
            f"- [{a['source']}] {a['title']}: {a['summary'][:200]}"
            for a in articles[:6]
        )

        prompt = f"""Recent AI news:
{context}

Write a DIFFERENTIATOR post. Choose ONE angle:
- Bold opinion: "That [AI tool/trend] is useless because..."
- Impact: "This update is bad news for [job role] because..."
- Viral curiosity: "This AI [did X] in [timeframe]..."

The post must be controversial enough to generate comments but factually grounded.

Return ONLY this JSON (no markdown, no extra text):
{{
  "topic": "the bold take in 5 words",
  "key_message": "the controversial hook (max 5 words, ALL CAPS, punchy)",
  "image_prompt": "bold visual concept for this opinion post (no text needed, just the mood/concept)",
  "twitter_text": "tweet version — bold hook first line, max 280 chars, ends with question to spark debate",
  "linkedin_text": "linkedin version — bold opener, build the argument, career impact, end with question (150-300 words)",
  "instagram_caption": "instagram version — bold hook, quick argument, career implication, question CTA",
  "instagram_hashtags": "15 relevant hashtags as a single string starting with space",
  "reel_script": "15-20 second spoken script delivering this bold take. Open with a shocking statement, back it up fast, end with a question. Conversational, no hashtags, max 60 words."
}}"""

        raw = self._call_claude(prompt)
        data = self._parse_json(raw)
        _save_posted_topic(data.get("topic", ""))
        logger.info(f"Differentiator Post generated: {data.get('topic', '')}")

        return GeneratedPost(
            post_type="differentiator",
            topic=data["topic"],
            twitter_text=data["twitter_text"],
            linkedin_text=data["linkedin_text"],
            instagram_caption=data["instagram_caption"],
            instagram_hashtags=data["instagram_hashtags"],
            image_prompt=data["image_prompt"],
            key_message=data["key_message"],
            reel_script=data.get("reel_script", ""),
        )

    def generate_all_posts(self, articles: list[dict]) -> list[GeneratedPost]:
        """Generate all 3 post types for today."""
        posts = []

        logger.info("Generating Daily Brief...")
        posts.append(self.write_daily_brief(articles))

        logger.info("Generating Learning Post...")
        posts.append(self.write_learning_post(articles))

        logger.info("Generating Differentiator Post...")
        posts.append(self.write_differentiator_post(articles))

        return posts
