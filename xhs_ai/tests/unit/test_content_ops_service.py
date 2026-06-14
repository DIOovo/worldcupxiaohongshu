import os
import sys
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
os.environ["HOME"] = tempfile.mkdtemp(prefix="xhs_ops_test_home_")

from src.core.models import Base
from src.core.models.user import User
from src.core.services.content_ops_service import ContentOpsService


def make_service_with_temp_db():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)

    class TempDbManager:
        def get_session_direct(self):
            return Session()

    service = ContentOpsService()
    service.db_manager = TempDbManager()

    session = Session()
    try:
        user = User(
            username="ops_user",
            phone="13800000001",
            display_name="运营用户",
            is_active=True,
            is_current=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        user_id = user.id
    finally:
        session.close()

    return service, db_path, user_id


def test_score_topic_returns_decision_fields():
    service, db_path, user_id = make_service_with_temp_db()
    try:
        result = service.score_topic(
            {
                "source": "weibo",
                "title": "AI工具如何提升职场女性效率",
                "rank": 3,
                "hot_value": 1200000,
            },
            user_id=user_id,
            persist=True,
        )

        assert result["id"] is not None
        assert result["heat_score"] > 0
        assert result["xhs_fit_score"] >= 35
        assert result["female_interest_score"] >= 38
        assert result["recommendation"] in {"优先选题", "可选题", "观察", "需改写降风险", "不建议发布"}
        assert "小红书" in result["xhs_angle"]
    finally:
        os.unlink(db_path)


def test_risk_review_flags_high_risk_claims():
    service, db_path, user_id = make_service_with_temp_db()
    try:
        result = service.review_risk("股票内幕保证稳赚", "网传这个方法唯一有效")

        assert result["decision"] in {"建议修改", "禁止发布"}
        assert result["risk_score"] >= 35
        assert result["hits"]["sensitive"]
    finally:
        os.unlink(db_path)


def test_style_profile_and_post_review_flow():
    service, db_path, user_id = make_service_with_temp_db()
    try:
        profile = service.create_style_profile(
            user_id,
            {
                "name": "理性分析型",
                "account_positioning": "AI工具和商业观察",
                "tone": "理性克制",
                "common_tags": ["AI工具", "职场成长"],
                "is_default": True,
            },
        )
        assert profile["is_default"] is True
        assert service.list_style_profiles(user_id)[0]["name"] == "理性分析型"

        post = service.create_post(
            user_id,
            {
                "style_profile_id": profile["id"],
                "title": "AI工具提升效率的3个方法",
                "content": "先从重复流程开始，再建立模板。",
                "tags": ["AI工具", "职场成长"],
                "status": "published",
            },
        )
        metric = service.record_post_metric(
            post["id"],
            {"views": 1000, "likes": 80, "collects": 40, "comments": 12, "shares": 5},
        )
        assert metric["engagement_score"] > 0

        review = service.analyze_posts(user_id)
        assert review["measured_post_count"] == 1
        assert review["top_posts"][0]["post"]["title"] == post["title"]
        assert review["best_tags"]
    finally:
        os.unlink(db_path)
