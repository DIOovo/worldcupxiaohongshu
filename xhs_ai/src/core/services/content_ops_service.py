"""
内容运营决策服务

提供热点评分、创作者风格档案、发布复盘等后台能力。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Any, Dict, List, Optional, Sequence

from src.config.database import db_manager
from src.core.models.content import CreatorStyleProfile, Post, PostMetric, TopicScore
from src.core.models.user import User
from src.core.services.hotspot_service import HotspotItem, hotspot_service
from src.core.services.user_service import user_service


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _listify(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        return [x.strip() for x in value.replace("，", ",").split(",") if x.strip()]
    return [str(value).strip()] if str(value).strip() else []


@dataclass(frozen=True)
class TopicScoreDraft:
    source: str
    title: str
    url: str = ""
    rank: Optional[int] = None
    hot_value: Optional[int] = None


class ContentOpsService:
    """内容运营后台能力。"""

    xhs_keywords = {
        "女性", "女生", "女孩", "妈妈", "宝妈", "职场", "副业", "成长", "情绪", "婚姻",
        "恋爱", "穿搭", "美妆", "护肤", "家居", "旅游", "减肥", "健康", "教育", "AI",
        "工具", "效率", "避坑", "清单", "攻略", "测评", "体验", "消费", "理财",
    }
    female_keywords = {"女性", "女生", "女孩", "妈妈", "宝妈", "婚姻", "恋爱", "穿搭", "美妆", "护肤", "减肥", "育儿", "职场"}
    monetize_keywords = {"课程", "培训", "工具", "AI", "副业", "理财", "消费", "测评", "模板", "咨询", "创业", "招聘", "旅游", "美妆"}
    controversy_keywords = {"争议", "道歉", "回应", "曝光", "怒", "骂", "造假", "翻车", "举报", "离婚", "判决", "冲突", "质疑"}
    risk_keywords = {"政治", "疫情", "医疗", "癌", "处方", "股票", "基金", "贷款", "博彩", "色情", "暴力", "谣言", "内幕", "绝对", "保证"}

    def __init__(self):
        self.db_manager = db_manager

    def score_hotspots(
        self,
        sources: Sequence[str],
        limit: int = 20,
        user_id: Optional[int] = None,
        persist: bool = True,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for source in sources:
            for item in hotspot_service.fetch(source, limit=limit):
                results.append(self.score_topic(item, user_id=user_id, persist=persist))
        return sorted(results, key=lambda x: x.get("total_score") or 0, reverse=True)

    def score_topic(
        self,
        item: HotspotItem | TopicScoreDraft | Dict[str, Any],
        user_id: Optional[int] = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        draft = self._normalize_topic(item)
        title = draft.title

        heat_score = self._score_heat(draft.rank, draft.hot_value)
        controversy_score = self._keyword_score(title, self.controversy_keywords, base=10, per_hit=18, cap=100)
        xhs_fit_score = self._score_xhs_fit(title)
        female_interest_score = self._keyword_score(title, self.female_keywords, base=20, per_hit=18, cap=95)
        monetization_score = self._keyword_score(title, self.monetize_keywords, base=25, per_hit=16, cap=95)
        risk_score = self._keyword_score(title, self.risk_keywords, base=8, per_hit=22, cap=100)

        total_score = round(
            heat_score * 0.28
            + controversy_score * 0.10
            + xhs_fit_score * 0.25
            + female_interest_score * 0.15
            + monetization_score * 0.15
            - risk_score * 0.18,
            2,
        )
        risk_level = self._risk_level(risk_score)
        recommendation = self._recommendation(total_score, risk_score)
        reasons = self._build_reasons(
            title,
            heat_score,
            xhs_fit_score,
            female_interest_score,
            monetization_score,
            controversy_score,
            risk_score,
        )

        data = {
            "source": draft.source,
            "title": title,
            "url": draft.url,
            "rank": draft.rank,
            "hot_value": draft.hot_value,
            "heat_score": heat_score,
            "controversy_score": controversy_score,
            "xhs_fit_score": xhs_fit_score,
            "female_interest_score": female_interest_score,
            "monetization_score": monetization_score,
            "risk_score": risk_score,
            "total_score": total_score,
            "risk_level": risk_level,
            "recommendation": recommendation,
            "xhs_angle": self.generate_xhs_angle(title),
            "reasons": reasons,
        }

        if persist:
            saved = self.create_topic_score(data, user_id=user_id)
            data["id"] = saved["id"]
            data["created_at"] = saved["created_at"]
            data["user_id"] = saved["user_id"]

        return data

    def review_risk(self, title: str, content: str = "") -> Dict[str, Any]:
        text = f"{title}\n{content}".strip()
        risk_hits = [kw for kw in sorted(self.risk_keywords) if kw.lower() in text.lower()]
        clickbait_hits = [kw for kw in ["震惊", "必看", "稳赚", "绝了", "封神", "全网最", "唯一", "保证"] if kw in text]
        unverified_hits = [kw for kw in ["据说", "网传", "疑似", "内幕", "未经证实"] if kw in text]

        score = min(100, len(risk_hits) * 22 + len(clickbait_hits) * 12 + len(unverified_hits) * 18)
        if score >= 70:
            decision = "禁止发布"
        elif score >= 35:
            decision = "建议修改"
        else:
            decision = "可发布"

        suggestions = []
        if risk_hits:
            suggestions.append("降低医疗、金融、政治等高风险表述，补充来源或改为经验分享。")
        if clickbait_hits:
            suggestions.append("弱化绝对化和标题党措辞，避免承诺结果。")
        if unverified_hits:
            suggestions.append("未经证实的信息需要标明来源，或改成观点讨论。")
        if not suggestions:
            suggestions.append("未发现明显高风险表达，发布前仍建议人工复核事实来源。")

        return {
            "decision": decision,
            "risk_score": score,
            "risk_level": self._risk_level(score),
            "hits": {
                "sensitive": risk_hits,
                "clickbait": clickbait_hits,
                "unverified": unverified_hits,
            },
            "suggestions": suggestions,
        }

    def create_style_profile(self, user_id: Optional[int], data: Dict[str, Any]) -> Dict[str, Any]:
        user_id = self._resolve_user_id(user_id)
        name = _clean_text(data.get("name")) or "默认风格"
        session = self.db_manager.get_session_direct()
        try:
            is_default = bool(data.get("is_default", False))
            if is_default:
                session.query(CreatorStyleProfile).filter(CreatorStyleProfile.user_id == user_id).update(
                    {CreatorStyleProfile.is_default: False}
                )
            profile = CreatorStyleProfile(
                user_id=user_id,
                name=name,
                account_positioning=_clean_text(data.get("account_positioning")),
                tone=_clean_text(data.get("tone")),
                banned_words=_listify(data.get("banned_words")),
                title_style=_clean_text(data.get("title_style")),
                target_audience=_clean_text(data.get("target_audience")),
                common_tags=_listify(data.get("common_tags")),
                viral_samples=_listify(data.get("viral_samples")),
                is_default=is_default,
            )
            session.add(profile)
            session.commit()
            session.refresh(profile)
            return profile.to_dict()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_style_profiles(self, user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        user_id = self._resolve_user_id(user_id)
        session = self.db_manager.get_session_direct()
        try:
            profiles = (
                session.query(CreatorStyleProfile)
                .filter(CreatorStyleProfile.user_id == user_id)
                .order_by(CreatorStyleProfile.is_default.desc(), CreatorStyleProfile.updated_at.desc())
                .all()
            )
            return [x.to_dict() for x in profiles]
        finally:
            session.close()

    def get_style_profile(self, profile_id: int) -> Optional[Dict[str, Any]]:
        session = self.db_manager.get_session_direct()
        try:
            profile = session.query(CreatorStyleProfile).filter(CreatorStyleProfile.id == profile_id).first()
            return profile.to_dict() if profile else None
        finally:
            session.close()

    def create_topic_score(self, data: Dict[str, Any], user_id: Optional[int] = None) -> Dict[str, Any]:
        session = self.db_manager.get_session_direct()
        try:
            score = TopicScore(
                user_id=user_id,
                source=_clean_text(data.get("source")) or "manual",
                title=_clean_text(data.get("title")),
                url=_clean_text(data.get("url")),
                rank=data.get("rank"),
                hot_value=data.get("hot_value"),
                heat_score=int(data.get("heat_score") or 0),
                controversy_score=int(data.get("controversy_score") or 0),
                xhs_fit_score=int(data.get("xhs_fit_score") or 0),
                female_interest_score=int(data.get("female_interest_score") or 0),
                monetization_score=int(data.get("monetization_score") or 0),
                risk_score=int(data.get("risk_score") or 0),
                total_score=float(data.get("total_score") or 0),
                risk_level=_clean_text(data.get("risk_level")) or "low",
                recommendation=_clean_text(data.get("recommendation")) or "可选题",
                xhs_angle=_clean_text(data.get("xhs_angle")),
                reasons=_listify(data.get("reasons")),
            )
            session.add(score)
            session.commit()
            session.refresh(score)
            return score.to_dict()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_topic_scores(self, user_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
        session = self.db_manager.get_session_direct()
        try:
            query = session.query(TopicScore)
            if user_id is not None:
                query = query.filter(TopicScore.user_id == user_id)
            rows = query.order_by(TopicScore.created_at.desc()).limit(max(1, int(limit))).all()
            return [x.to_dict() for x in rows]
        finally:
            session.close()

    def create_post(self, user_id: Optional[int], data: Dict[str, Any]) -> Dict[str, Any]:
        user_id = self._resolve_user_id(user_id)
        title = _clean_text(data.get("title"))
        content = _clean_text(data.get("content"))
        if not title:
            raise ValueError("标题不能为空")
        if not content:
            raise ValueError("正文不能为空")

        session = self.db_manager.get_session_direct()
        try:
            published_at = self._parse_datetime(data.get("published_at"))
            post = Post(
                user_id=user_id,
                topic_score_id=data.get("topic_score_id"),
                style_profile_id=data.get("style_profile_id"),
                platform=_clean_text(data.get("platform")) or "xiaohongshu",
                title=title,
                content=content,
                tags=_listify(data.get("tags")),
                publish_url=_clean_text(data.get("publish_url")),
                status=_clean_text(data.get("status")) or "draft",
                published_at=published_at,
            )
            session.add(post)
            session.commit()
            session.refresh(post)
            return post.to_dict()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def list_posts(self, user_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
        user_id = self._resolve_user_id(user_id)
        session = self.db_manager.get_session_direct()
        try:
            rows = (
                session.query(Post)
                .filter(Post.user_id == user_id)
                .order_by(Post.created_at.desc())
                .limit(max(1, int(limit)))
                .all()
            )
            return [x.to_dict() for x in rows]
        finally:
            session.close()

    def record_post_metric(self, post_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        session = self.db_manager.get_session_direct()
        try:
            post = session.query(Post).filter(Post.id == int(post_id)).first()
            if not post:
                raise ValueError(f"帖子ID {post_id} 不存在")
            metric = PostMetric(
                post_id=post.id,
                views=int(data.get("views") or 0),
                likes=int(data.get("likes") or 0),
                collects=int(data.get("collects") or 0),
                comments=int(data.get("comments") or 0),
                shares=int(data.get("shares") or 0),
                followers_gain=int(data.get("followers_gain") or 0),
                notes=_clean_text(data.get("notes")),
            )
            metric.engagement_score = self._engagement_score(metric)
            session.add(metric)
            session.commit()
            session.refresh(metric)
            return metric.to_dict()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def analyze_posts(self, user_id: Optional[int] = None, limit: int = 100) -> Dict[str, Any]:
        user_id = self._resolve_user_id(user_id)
        session = self.db_manager.get_session_direct()
        try:
            posts = (
                session.query(Post)
                .filter(Post.user_id == user_id)
                .order_by(Post.created_at.desc())
                .limit(max(1, int(limit)))
                .all()
            )
            scored = []
            tag_scores: Dict[str, List[float]] = {}
            for post in posts:
                if not post.metrics:
                    continue
                latest = sorted(post.metrics, key=lambda x: x.recorded_at or datetime.min, reverse=True)[0]
                scored.append({"post": post.to_dict(), "metric": latest.to_dict()})
                for tag in post.tags or []:
                    tag_scores.setdefault(tag, []).append(float(latest.engagement_score or 0))

            top_posts = sorted(scored, key=lambda x: x["metric"].get("engagement_score") or 0, reverse=True)[:10]
            best_tags = sorted(
                (
                    {"tag": tag, "avg_engagement_score": round(sum(vals) / len(vals), 2), "count": len(vals)}
                    for tag, vals in tag_scores.items()
                    if vals
                ),
                key=lambda x: x["avg_engagement_score"],
                reverse=True,
            )[:10]

            return {
                "post_count": len(posts),
                "measured_post_count": len(scored),
                "top_posts": top_posts,
                "best_tags": best_tags,
                "suggestions": self._analysis_suggestions(top_posts, best_tags),
            }
        finally:
            session.close()

    def generate_xhs_angle(self, title: str, style_profile: Optional[Dict[str, Any]] = None) -> str:
        title = _clean_text(title)
        positioning = _clean_text((style_profile or {}).get("account_positioning"))
        audience = _clean_text((style_profile or {}).get("target_audience")) or "小红书用户"
        if positioning:
            return f"从「{positioning}」角度切入，把「{title}」拆成{audience}能直接使用的经验、避坑清单和行动建议。"
        return f"把「{title}」改写成小红书选题：先讲普通人为什么要关心，再给出3个判断依据和可执行建议。"

    def _normalize_topic(self, item: HotspotItem | TopicScoreDraft | Dict[str, Any]) -> TopicScoreDraft:
        if isinstance(item, HotspotItem):
            return TopicScoreDraft(item.source, item.title, item.url, item.rank, item.hot)
        if isinstance(item, TopicScoreDraft):
            return item
        return TopicScoreDraft(
            source=_clean_text(item.get("source")) or "manual",
            title=_clean_text(item.get("title")),
            url=_clean_text(item.get("url")),
            rank=item.get("rank"),
            hot_value=item.get("hot") or item.get("hot_value"),
        )

    def _score_heat(self, rank: Optional[int], hot_value: Optional[int]) -> int:
        rank_score = 50
        if rank:
            rank_score = max(20, 100 - (int(rank) - 1) * 3)
        hot_score = 0
        if hot_value:
            hot_score = min(100, int(math.log10(max(10, int(hot_value))) * 18))
        return int(max(rank_score, hot_score))

    def _score_xhs_fit(self, title: str) -> int:
        base = 35
        hit_count = sum(1 for kw in self.xhs_keywords if kw.lower() in title.lower())
        score = base + hit_count * 12
        if any(x in title for x in ["怎么", "为何", "为什么", "如何", "建议", "清单", "攻略"]):
            score += 12
        if len(title) <= 24:
            score += 8
        return min(100, score)

    @staticmethod
    def _keyword_score(title: str, keywords: set[str], base: int, per_hit: int, cap: int) -> int:
        hit_count = sum(1 for kw in keywords if kw.lower() in title.lower())
        return min(cap, base + hit_count * per_hit)

    @staticmethod
    def _risk_level(score: int) -> str:
        if score >= 70:
            return "high"
        if score >= 35:
            return "medium"
        return "low"

    @staticmethod
    def _recommendation(total_score: float, risk_score: int) -> str:
        if risk_score >= 70:
            return "不建议发布"
        if risk_score >= 35:
            return "需改写降风险"
        if total_score >= 65:
            return "优先选题"
        if total_score >= 45:
            return "可选题"
        return "观察"

    @staticmethod
    def _build_reasons(
        title: str,
        heat_score: int,
        xhs_fit_score: int,
        female_interest_score: int,
        monetization_score: int,
        controversy_score: int,
        risk_score: int,
    ) -> List[str]:
        reasons = []
        if heat_score >= 75:
            reasons.append("榜单位置或热度值较高，适合作为即时选题。")
        if xhs_fit_score >= 65:
            reasons.append("话题具备经验分享、清单或避坑改写空间。")
        if female_interest_score >= 55:
            reasons.append("包含女性用户、生活方式或职场成长相关信号。")
        if monetization_score >= 55:
            reasons.append("存在工具、课程、咨询或消费决策等商业延展空间。")
        if controversy_score >= 45:
            reasons.append("话题有讨论张力，但需要控制表达尺度。")
        if risk_score >= 35:
            reasons.append("包含敏感或高承诺表达，发布前需要降风险审核。")
        if not reasons:
            reasons.append(f"「{title}」可作为普通热点观察，建议补充具体人群痛点后再生成。")
        return reasons

    @staticmethod
    def _engagement_score(metric: PostMetric) -> float:
        views = max(1, int(metric.views or 0))
        weighted = (
            int(metric.likes or 0) * 1.0
            + int(metric.collects or 0) * 1.8
            + int(metric.comments or 0) * 2.2
            + int(metric.shares or 0) * 2.5
            + int(metric.followers_gain or 0) * 3.0
        )
        return round(weighted / views * 1000, 2)

    @staticmethod
    def _analysis_suggestions(top_posts: List[Dict[str, Any]], best_tags: List[Dict[str, Any]]) -> List[str]:
        suggestions = []
        if top_posts:
            suggestions.append("优先复用高互动帖子的标题结构、发布时间和标签组合。")
        if best_tags:
            tag_names = "、".join(x["tag"] for x in best_tags[:3])
            suggestions.append(f"近期高表现标签集中在：{tag_names}。")
        if not suggestions:
            suggestions.append("复盘样本不足，先持续记录至少5篇内容的浏览、点赞、收藏和评论。")
        return suggestions

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return None

    @staticmethod
    def _resolve_user_id(user_id: Optional[int]) -> int:
        if user_id:
            return int(user_id)
        user: Optional[User] = user_service.get_current_user()
        if not user:
            raise ValueError("没有可用用户")
        return int(user.id)


content_ops_service = ContentOpsService()
