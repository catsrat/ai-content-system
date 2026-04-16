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
    post_type: str          # daily_brief | learning | differentiator | workflow
    topic: str
    twitter_text: str
    linkedin_text: str
    instagram_caption: str
    instagram_hashtags: str
    image_prompt: str       # prompt for Canva/image generation
    key_message: str        # 1-line summary for image headline
    reel_script: str        # 15-25 second voiceover script for Reels
    reel_slides: list = None  # 4-5 short slide texts for visual display in reel
    workflow_detail: str = ""  # full step-by-step workflow guide (workflow posts only)


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
        """Call Claude and return full text response."""
        with self.client.messages.stream(
            model="claude-opus-4-6",
            max_tokens=4096,
            system=self.system,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            text = stream.get_final_text().strip()
        if not text:
            raise ValueError("Claude returned an empty response")
        return text

    def _parse_json(self, raw: str) -> dict:
        """Extract and parse JSON from Claude's response."""
        if not raw:
            raise ValueError("Empty response from Claude")
        # Strip markdown code fences if present
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0]
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0]
        raw = raw.strip()
        logger.debug(f"Parsing JSON ({len(raw)} chars): {raw[:100]}...")
        return json.loads(raw)

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
  "reel_script": "15-20 second spoken script for a news anchor voiceover. Start with a hook, deliver the key fact, explain why it matters for careers. Conversational, no hashtags, no emojis. Max 60 words.",
  "reel_slides": ["hook line (max 4 words, ALL CAPS)", "key fact (max 5 words)", "why it matters (max 5 words)", "call to action (max 4 words)"]
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
            reel_slides=data.get("reel_slides", []),
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
  "reel_script": "15-20 second spoken script teaching this skill. Start with a hook, explain concept in simple terms, give one action step. Conversational, no hashtags, max 60 words.",
  "reel_slides": ["hook (max 4 words, ALL CAPS)", "what it does (max 5 words)", "real example (max 5 words)", "action step (max 4 words)"]
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
            reel_slides=data.get("reel_slides", []),
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
  "reel_script": "15-20 second spoken script delivering this bold take. Open with a shocking statement, back it up fast, end with a question. Conversational, no hashtags, max 60 words.",
  "reel_slides": ["shocking hook (max 4 words, ALL CAPS)", "the bold claim (max 5 words)", "the proof (max 5 words)", "the question (max 5 words)"]
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
            reel_slides=data.get("reel_slides", []),
        )

    def write_workflow_post(self, workflow_ideas: list[dict]) -> GeneratedPost:
        """Generate an AI Workflow post — free tool use case with comment DM trigger."""
        posted = _load_posted_topics()
        posted_str = ", ".join(posted[-10:]) if posted else "none"

        ideas_text = "\n".join(
            f"- [{w['source']}] {w['title']}: {w['summary'][:200]}"
            for w in workflow_ideas[:6]
        )

        prompt = f"""You are creating an AI WORKFLOW post for @AI_TECH_NEWSS.

These are real AI tool use cases and workflow ideas from Reddit and AI communities:
{ideas_text}

Already posted about these recently (DO NOT repeat): {posted_str}

Pick the MOST valuable and surprising free AI workflow from the list above.
The post must make people think "I didn't know I could do that for free!"

The CTA must be: "Comment DM and I'll send you the full step-by-step workflow"

Return ONLY this JSON (no markdown, no extra text):
{{
  "topic": "the workflow in 5 words",
  "key_message": "Use [AI Tool] For Free (max 5 words, ALL CAPS)",
  "image_prompt": "visual concept for this workflow post — show the AI tool being used productively",
  "twitter_text": "tweet version — hook about free AI tool, what it replaces, max 280 chars",
  "linkedin_text": "linkedin version — hook, what the tool does, 3 bullet use cases, CTA to comment DM (150-200 words)",
  "instagram_caption": "instagram caption — hook line, tease the workflow, 'Comment DM and I'll send you the full step-by-step workflow 👇'",
  "instagram_hashtags": "15 relevant hashtags as a single string starting with space",
  "reel_script": "15-20 second voiceover: hook about the free AI tool, what most people pay for that this replaces, one specific example of what it can do, end with 'Comment DM for the full workflow'. Max 60 words.",
  "reel_slides": ["hook (max 4 words, ALL CAPS)", "what it replaces (max 5 words)", "what it does free (max 5 words)", "COMMENT DM BELOW"],
  "workflow_detail": "the actual full step-by-step workflow to send via DM (5-8 steps, practical, specific)"
}}"""

        raw = self._call_claude(prompt)
        data = self._parse_json(raw)
        _save_posted_topic(data.get("topic", ""))
        logger.info(f"Workflow Post generated: {data.get('topic', '')}")

        workflow_detail = data.get("workflow_detail") or data.get("workflow_steps") or ""
        logger.info(f"Workflow detail in response: {len(workflow_detail)} chars")

        # Save the full workflow guide to a text file for ManyChat DMs
        if workflow_detail:
            try:
                guides_dir = os.path.join(os.path.dirname(__file__), "..", "output", "workflows")
                os.makedirs(guides_dir, exist_ok=True)
                from datetime import datetime
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_topic = data["topic"].replace(" ", "_").replace("/", "-")[:40]
                guide_path = os.path.join(guides_dir, f"{safe_topic}_{timestamp}.txt")
                with open(guide_path, "w") as f:
                    f.write(f"WORKFLOW: {data['topic']}\n")
                    f.write("=" * 60 + "\n\n")
                    f.write(workflow_detail)
                    f.write("\n\n---\nGenerated by AI_TECH_NEWSS\n")
                logger.info(f"Workflow guide saved: {guide_path}")
            except Exception as e:
                logger.warning(f"Could not save workflow guide: {e}")

        return GeneratedPost(
            post_type="workflow",
            topic=data["topic"],
            twitter_text=data["twitter_text"],
            linkedin_text=data["linkedin_text"],
            instagram_caption=data["instagram_caption"],
            instagram_hashtags=data["instagram_hashtags"],
            image_prompt=data["image_prompt"],
            key_message=data["key_message"],
            reel_script=data.get("reel_script", ""),
            reel_slides=data.get("reel_slides", []),
            workflow_detail=workflow_detail,
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
