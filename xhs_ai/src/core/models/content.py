"""
内容管理相关数据模型
包含内容模板、发布历史、定时任务等模型
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, ForeignKey, JSON, Float
from sqlalchemy.orm import relationship

# 从user模块导入Base
from .user import Base


class ContentTemplate(Base):
    """内容模板模型"""
    __tablename__ = 'content_templates'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, comment='用户ID')
    name = Column(String(100), nullable=False, comment='模板名称')
    title = Column(String(200), comment='标题模板')
    content = Column(Text, comment='内容模板')
    tags = Column(Text, comment='标签（JSON数组）')
    category = Column(String(50), comment='分类')
    is_active = Column(Boolean, default=True, comment='是否启用')
    created_at = Column(DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')
    
    # 关联关系
    user = relationship("User", back_populates="content_templates")
    
    def __repr__(self):
        return f"<ContentTemplate(id={self.id}, name='{self.name}', user_id={self.user_id})>"
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'title': self.title,
            'content': self.content,
            'tags': self.tags,
            'category': self.category,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class PublishHistory(Base):
    """发布历史模型"""
    __tablename__ = 'publish_history'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, comment='用户ID')
    template_id = Column(Integer, ForeignKey('content_templates.id'), comment='模板ID')
    title = Column(String(200), nullable=False, comment='发布标题')
    content = Column(Text, nullable=False, comment='发布内容')
    platform = Column(String(50), nullable=False, comment='发布平台')
    status = Column(String(20), default='pending', comment='发布状态: pending, success, failed')
    publish_url = Column(String(500), comment='发布链接')
    error_message = Column(Text, comment='错误信息')
    publish_time = Column(DateTime, comment='发布时间')
    created_at = Column(DateTime, default=datetime.utcnow, comment='创建时间')
    
    # 关联关系
    user = relationship("User", back_populates="publish_history")
    template = relationship("ContentTemplate")
    
    def __repr__(self):
        return f"<PublishHistory(id={self.id}, title='{self.title}', platform='{self.platform}')>"
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'template_id': self.template_id,
            'title': self.title,
            'content': self.content,
            'platform': self.platform,
            'status': self.status,
            'publish_url': self.publish_url,
            'error_message': self.error_message,
            'publish_time': self.publish_time.isoformat() if self.publish_time else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class ScheduledTask(Base):
    """定时任务模型"""
    __tablename__ = 'scheduled_tasks'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, comment='用户ID')
    template_id = Column(Integer, ForeignKey('content_templates.id'), comment='模板ID')
    name = Column(String(100), nullable=False, comment='任务名称')
    platform = Column(String(50), nullable=False, comment='发布平台')
    schedule_type = Column(String(20), default='once', comment='调度类型: once, daily, weekly, monthly')
    schedule_time = Column(DateTime, nullable=False, comment='调度时间')
    is_active = Column(Boolean, default=True, comment='是否启用')
    last_run_time = Column(DateTime, comment='最后运行时间')
    next_run_time = Column(DateTime, comment='下次运行时间')
    run_count = Column(Integer, default=0, comment='运行次数')
    created_at = Column(DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')
    
    # 关联关系
    user = relationship("User", back_populates="scheduled_tasks")
    template = relationship("ContentTemplate")
    
    def __repr__(self):
        return f"<ScheduledTask(id={self.id}, name='{self.name}', platform='{self.platform}')>"
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'template_id': self.template_id,
            'name': self.name,
            'platform': self.platform,
            'schedule_type': self.schedule_type,
            'schedule_time': self.schedule_time.isoformat() if self.schedule_time else None,
            'is_active': self.is_active,
            'last_run_time': self.last_run_time.isoformat() if self.last_run_time else None,
            'next_run_time': self.next_run_time.isoformat() if self.next_run_time else None,
            'run_count': self.run_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        } 


class CreatorStyleProfile(Base):
    """创作者风格档案"""
    __tablename__ = 'creator_style_profiles'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, comment='用户ID')
    name = Column(String(100), nullable=False, comment='风格名称')
    account_positioning = Column(Text, comment='账号定位')
    tone = Column(String(100), comment='常用语气')
    banned_words = Column(JSON, default=list, comment='禁用词')
    title_style = Column(Text, comment='标题风格')
    target_audience = Column(Text, comment='目标人群')
    common_tags = Column(JSON, default=list, comment='常用标签')
    viral_samples = Column(JSON, default=list, comment='爆款样本文案')
    is_default = Column(Boolean, default=False, comment='是否默认')
    created_at = Column(DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')

    user = relationship("User", back_populates="creator_style_profiles")

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'account_positioning': self.account_positioning,
            'tone': self.tone,
            'banned_words': self.banned_words or [],
            'title_style': self.title_style,
            'target_audience': self.target_audience,
            'common_tags': self.common_tags or [],
            'viral_samples': self.viral_samples or [],
            'is_default': self.is_default,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class TopicScore(Base):
    """热点评分记录"""
    __tablename__ = 'topic_scores'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True, comment='用户ID')
    source = Column(String(50), nullable=False, comment='热点来源')
    title = Column(String(300), nullable=False, comment='热点标题')
    url = Column(String(500), comment='热点链接')
    rank = Column(Integer, comment='榜单排名')
    hot_value = Column(Integer, comment='原始热度值')
    heat_score = Column(Integer, default=0, comment='热度分')
    controversy_score = Column(Integer, default=0, comment='争议度')
    xhs_fit_score = Column(Integer, default=0, comment='小红书适配度')
    female_interest_score = Column(Integer, default=0, comment='女性用户关注度')
    monetization_score = Column(Integer, default=0, comment='商业变现潜力')
    risk_score = Column(Integer, default=0, comment='风险等级分')
    total_score = Column(Float, default=0, comment='综合分')
    risk_level = Column(String(20), default='low', comment='风险等级')
    recommendation = Column(String(20), default='可选题', comment='建议')
    xhs_angle = Column(Text, comment='小红书切入角度')
    reasons = Column(JSON, default=list, comment='评分原因')
    created_at = Column(DateTime, default=datetime.utcnow, comment='创建时间')

    user = relationship("User", back_populates="topic_scores")

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'source': self.source,
            'title': self.title,
            'url': self.url,
            'rank': self.rank,
            'hot_value': self.hot_value,
            'heat_score': self.heat_score,
            'controversy_score': self.controversy_score,
            'xhs_fit_score': self.xhs_fit_score,
            'female_interest_score': self.female_interest_score,
            'monetization_score': self.monetization_score,
            'risk_score': self.risk_score,
            'total_score': self.total_score,
            'risk_level': self.risk_level,
            'recommendation': self.recommendation,
            'xhs_angle': self.xhs_angle,
            'reasons': self.reasons or [],
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }


class Post(Base):
    """运营复盘帖子记录"""
    __tablename__ = 'posts'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, comment='用户ID')
    topic_score_id = Column(Integer, ForeignKey('topic_scores.id'), comment='选题评分ID')
    style_profile_id = Column(Integer, ForeignKey('creator_style_profiles.id'), comment='风格档案ID')
    platform = Column(String(50), default='xiaohongshu', comment='平台')
    title = Column(String(300), nullable=False, comment='标题')
    content = Column(Text, nullable=False, comment='正文')
    tags = Column(JSON, default=list, comment='标签')
    publish_url = Column(String(500), comment='发布链接')
    status = Column(String(30), default='draft', comment='状态')
    published_at = Column(DateTime, comment='发布时间')
    created_at = Column(DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')

    user = relationship("User", back_populates="posts")
    metrics = relationship("PostMetric", back_populates="post", cascade="all, delete-orphan")

    def to_dict(self):
        latest_metric = None
        if self.metrics:
            latest_metric = sorted(self.metrics, key=lambda x: x.recorded_at or datetime.min, reverse=True)[0]
        return {
            'id': self.id,
            'user_id': self.user_id,
            'topic_score_id': self.topic_score_id,
            'style_profile_id': self.style_profile_id,
            'platform': self.platform,
            'title': self.title,
            'content': self.content,
            'tags': self.tags or [],
            'publish_url': self.publish_url,
            'status': self.status,
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'latest_metric': latest_metric.to_dict() if latest_metric else None,
        }


class PostMetric(Base):
    """帖子效果指标"""
    __tablename__ = 'post_metrics'

    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, ForeignKey('posts.id'), nullable=False, comment='帖子ID')
    views = Column(Integer, default=0, comment='浏览量')
    likes = Column(Integer, default=0, comment='点赞')
    collects = Column(Integer, default=0, comment='收藏')
    comments = Column(Integer, default=0, comment='评论')
    shares = Column(Integer, default=0, comment='分享')
    followers_gain = Column(Integer, default=0, comment='涨粉')
    engagement_score = Column(Float, default=0, comment='互动分')
    notes = Column(Text, comment='复盘备注')
    recorded_at = Column(DateTime, default=datetime.utcnow, comment='记录时间')

    post = relationship("Post", back_populates="metrics")

    def to_dict(self):
        return {
            'id': self.id,
            'post_id': self.post_id,
            'views': self.views,
            'likes': self.likes,
            'collects': self.collects,
            'comments': self.comments,
            'shares': self.shares,
            'followers_gain': self.followers_gain,
            'engagement_score': self.engagement_score,
            'notes': self.notes,
            'recorded_at': self.recorded_at.isoformat() if self.recorded_at else None,
        }


class StyleExperiment(Base):
    """风格实验记录"""
    __tablename__ = 'style_experiments'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False, comment='用户ID')
    name = Column(String(100), nullable=False, comment='实验名称')
    hypothesis = Column(Text, comment='实验假设')
    style_profile_id = Column(Integer, ForeignKey('creator_style_profiles.id'), comment='风格档案ID')
    status = Column(String(30), default='running', comment='状态')
    summary = Column(Text, comment='结论')
    created_at = Column(DateTime, default=datetime.utcnow, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment='更新时间')

    user = relationship("User", back_populates="style_experiments")

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'name': self.name,
            'hypothesis': self.hypothesis,
            'style_profile_id': self.style_profile_id,
            'status': self.status,
            'summary': self.summary,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
