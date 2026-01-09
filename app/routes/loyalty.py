"""
Loyalty Routes
Gamified loyalty system with badges, challenges, and referrals
"""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models import db, Customer, Sale, SaleItem
from app.models_extended import (
    LoyaltyBadge, CustomerBadge, LoyaltyChallenge,
    CustomerChallengeProgress, Referral, seed_default_badges
)
from datetime import datetime, timedelta
from sqlalchemy import func
import secrets

bp = Blueprint('loyalty', __name__)


# Badge checking and awarding functions
def check_and_award_badges(customer_id, sale=None):
    """
    Check if customer qualifies for any badges and award them
    Returns list of newly awarded badges
    """
    customer = Customer.query.get(customer_id)
    if not customer:
        return []

    new_badges = []

    # Get all active badges customer doesn't have
    existing_badge_ids = db.session.query(CustomerBadge.badge_id).filter_by(
        customer_id=customer_id
    ).all()
    existing_badge_ids = [b[0] for b in existing_badge_ids]

    available_badges = LoyaltyBadge.query.filter(
        LoyaltyBadge.is_active == True,
        ~LoyaltyBadge.id.in_(existing_badge_ids) if existing_badge_ids else True
    ).all()

    for badge in available_badges:
        earned = False

        if badge.criteria_type == 'first_purchase':
            # Check if this is customer's first purchase
            purchase_count = Sale.query.filter_by(customer_id=customer_id).count()
            if purchase_count == 1:
                earned = True

        elif badge.criteria_type == 'purchase_count':
            # Check total purchase count
            purchase_count = Sale.query.filter_by(customer_id=customer_id).count()
            if purchase_count >= badge.criteria_value:
                earned = True

        elif badge.criteria_type == 'spend_amount':
            # Check total spending
            total_spent = db.session.query(func.sum(Sale.total)).filter_by(
                customer_id=customer_id
            ).scalar() or 0
            if total_spent >= badge.criteria_value:
                earned = True

        elif badge.criteria_type == 'single_purchase':
            # Check if current sale meets the amount
            if sale and sale.total >= badge.criteria_value:
                earned = True

        elif badge.criteria_type == 'loyalty_tier':
            # Check loyalty tier (1=Bronze, 2=Silver, 3=Gold, 4=Platinum)
            tier_map = {'bronze': 1, 'silver': 2, 'gold': 3, 'platinum': 4}
            customer_tier = tier_map.get(customer.loyalty_tier.lower(), 1)
            if customer_tier >= badge.criteria_value:
                earned = True

        elif badge.criteria_type == 'referral':
            # Check referral count
            referral_count = Referral.query.filter_by(
                referrer_id=customer_id,
                status='completed'
            ).count()
            if referral_count >= badge.criteria_value:
                earned = True

        elif badge.criteria_type == 'category_purchase':
            # Check if customer bought from specific category (criteria_value is category_id)
            if sale:
                for item in sale.items:
                    if item.product.category_id == badge.criteria_value:
                        earned = True
                        break

        elif badge.criteria_type == 'points_milestone':
            # Check if customer reached points milestone
            if customer.loyalty_points >= badge.criteria_value:
                earned = True

        if earned:
            # Award the badge
            customer_badge = CustomerBadge(
                customer_id=customer_id,
                badge_id=badge.id,
                earned_at=datetime.utcnow()
            )
            db.session.add(customer_badge)

            # Award bonus points if any
            if badge.points_reward and badge.points_reward > 0:
                customer.loyalty_points = (customer.loyalty_points or 0) + badge.points_reward

            new_badges.append({
                'id': badge.id,
                'name': badge.name,
                'description': badge.description,
                'icon': badge.icon,
                'color': badge.color,
                'points_reward': badge.points_reward
            })

    if new_badges:
        db.session.commit()

    return new_badges


def update_challenge_progress(customer_id, sale=None):
    """
    Update progress on active challenges for a customer
    Returns list of completed challenges
    """
    customer = Customer.query.get(customer_id)
    if not customer:
        return []

    completed_challenges = []

    # Get active challenges
    active_challenges = LoyaltyChallenge.query.filter(
        LoyaltyChallenge.is_active == True,
        LoyaltyChallenge.start_date <= datetime.utcnow(),
        LoyaltyChallenge.end_date >= datetime.utcnow()
    ).all()

    for challenge in active_challenges:
        # Get or create progress record
        progress = CustomerChallengeProgress.query.filter_by(
            customer_id=customer_id,
            challenge_id=challenge.id
        ).first()

        if not progress:
            progress = CustomerChallengeProgress(
                customer_id=customer_id,
                challenge_id=challenge.id,
                current_value=0
            )
            db.session.add(progress)

        if progress.completed:
            continue

        # Update progress based on challenge type
        if challenge.challenge_type == 'spending_goal':
            if sale:
                progress.current_value = (progress.current_value or 0) + float(sale.total)

        elif challenge.challenge_type == 'visit_count':
            if sale:
                progress.current_value = (progress.current_value or 0) + 1

        elif challenge.challenge_type == 'referral_count':
            referral_count = Referral.query.filter_by(
                referrer_id=customer_id,
                status='completed'
            ).count()
            progress.current_value = referral_count

        elif challenge.challenge_type == 'product_count':
            if sale:
                items_count = sum(item.quantity for item in sale.items)
                progress.current_value = (progress.current_value or 0) + items_count

        # Check if challenge completed
        if progress.current_value >= challenge.target_value:
            progress.completed = True
            progress.completed_at = datetime.utcnow()

            # Award reward
            if challenge.reward_type == 'points':
                customer.loyalty_points = (customer.loyalty_points or 0) + challenge.reward_value
            elif challenge.reward_type == 'badge':
                # Award badge by ID in reward_value
                badge = LoyaltyBadge.query.get(challenge.reward_value)
                if badge:
                    existing = CustomerBadge.query.filter_by(
                        customer_id=customer_id,
                        badge_id=badge.id
                    ).first()
                    if not existing:
                        customer_badge = CustomerBadge(
                            customer_id=customer_id,
                            badge_id=badge.id,
                            earned_at=datetime.utcnow()
                        )
                        db.session.add(customer_badge)

            completed_challenges.append({
                'id': challenge.id,
                'name': challenge.name,
                'reward_type': challenge.reward_type,
                'reward_value': challenge.reward_value
            })

    db.session.commit()
    return completed_challenges


def generate_referral_code(customer_id):
    """Generate a unique referral code for a customer"""
    customer = Customer.query.get(customer_id)
    if not customer:
        return None

    if customer.referral_code:
        return customer.referral_code

    # Generate code based on customer name and random suffix
    name_part = ''.join(c for c in customer.name if c.isalnum())[:4].upper()
    random_part = secrets.token_hex(3).upper()
    code = f"{name_part}{random_part}"

    # Ensure unique
    while Customer.query.filter_by(referral_code=code).first():
        random_part = secrets.token_hex(3).upper()
        code = f"{name_part}{random_part}"

    customer.referral_code = code
    db.session.commit()

    return code


def process_referral(referral_code, new_customer_id):
    """Process a referral when a new customer makes their first purchase"""
    referrer = Customer.query.filter_by(referral_code=referral_code).first()
    if not referrer:
        return None

    new_customer = Customer.query.get(new_customer_id)
    if not new_customer or referrer.id == new_customer.id:
        return None

    # Check if referral already exists
    existing = Referral.query.filter_by(
        referred_id=new_customer_id
    ).first()
    if existing:
        return None

    # Create referral record
    referral = Referral(
        referrer_id=referrer.id,
        referred_id=new_customer_id,
        referral_code=referral_code,
        status='completed',
        referrer_reward=100,  # Default 100 points
        referred_reward=50,   # Default 50 points
        completed_at=datetime.utcnow()
    )
    db.session.add(referral)

    # Award points to both
    referrer.loyalty_points = (referrer.loyalty_points or 0) + referral.referrer_reward
    new_customer.loyalty_points = (new_customer.loyalty_points or 0) + referral.referred_reward

    db.session.commit()

    # Check for referral badges
    check_and_award_badges(referrer.id)

    return referral


# Admin routes for badge management
@bp.route('/badges')
@login_required
def badges():
    """List all badges"""
    if current_user.role not in ['admin', 'manager']:
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    badges = LoyaltyBadge.query.order_by(LoyaltyBadge.criteria_type).all()

    # Count how many customers have each badge
    badge_stats = {}
    for badge in badges:
        count = CustomerBadge.query.filter_by(badge_id=badge.id).count()
        badge_stats[badge.id] = count

    return render_template('loyalty/badges.html', badges=badges, badge_stats=badge_stats)


@bp.route('/badges/create', methods=['GET', 'POST'])
@login_required
def create_badge():
    """Create a new badge"""
    if current_user.role not in ['admin', 'manager']:
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        badge = LoyaltyBadge(
            code=request.form.get('code'),
            name=request.form.get('name'),
            description=request.form.get('description'),
            badge_type=request.form.get('badge_type', 'milestone'),
            icon=request.form.get('icon', 'fas fa-award'),
            color=request.form.get('color', '#FFD700'),
            criteria_type=request.form.get('criteria_type'),
            criteria_value=int(request.form.get('criteria_value', 0) or 0),
            points_reward=int(request.form.get('points_reward', 0) or 0),
            is_active=True
        )
        db.session.add(badge)
        db.session.commit()
        flash(f'Badge "{badge.name}" created successfully!', 'success')
        return redirect(url_for('loyalty.badges'))

    return render_template('loyalty/create_badge.html')


@bp.route('/badges/<int:badge_id>/toggle', methods=['POST'])
@login_required
def toggle_badge(badge_id):
    """Toggle badge active status"""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    badge = LoyaltyBadge.query.get_or_404(badge_id)
    badge.is_active = not badge.is_active
    db.session.commit()

    return jsonify({'success': True, 'is_active': badge.is_active})


@bp.route('/badges/seed', methods=['POST'])
@login_required
def seed_badges():
    """Seed default badges"""
    if current_user.role != 'admin':
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    count = seed_default_badges()
    return jsonify({'success': True, 'count': count, 'message': f'{count} badges seeded'})


# Admin routes for challenge management
@bp.route('/challenges')
@login_required
def challenges():
    """List all challenges"""
    if current_user.role not in ['admin', 'manager']:
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    challenges = LoyaltyChallenge.query.order_by(LoyaltyChallenge.end_date.desc()).all()

    # Get participation stats
    challenge_stats = {}
    for challenge in challenges:
        total = CustomerChallengeProgress.query.filter_by(challenge_id=challenge.id).count()
        completed = CustomerChallengeProgress.query.filter_by(
            challenge_id=challenge.id,
            completed=True
        ).count()
        challenge_stats[challenge.id] = {'total': total, 'completed': completed}

    return render_template('loyalty/challenges.html', challenges=challenges, challenge_stats=challenge_stats)


@bp.route('/challenges/create', methods=['GET', 'POST'])
@login_required
def create_challenge():
    """Create a new challenge"""
    if current_user.role not in ['admin', 'manager']:
        flash('Access denied', 'error')
        return redirect(url_for('index'))

    if request.method == 'POST':
        challenge = LoyaltyChallenge(
            name=request.form.get('name'),
            description=request.form.get('description'),
            challenge_type=request.form.get('challenge_type'),
            target_value=int(request.form.get('target_value', 0)),
            start_date=datetime.strptime(request.form.get('start_date'), '%Y-%m-%d'),
            end_date=datetime.strptime(request.form.get('end_date'), '%Y-%m-%d'),
            reward_type=request.form.get('reward_type', 'points'),
            reward_value=int(request.form.get('reward_value', 0)),
            is_active=True
        )
        db.session.add(challenge)
        db.session.commit()
        flash(f'Challenge "{challenge.name}" created successfully!', 'success')
        return redirect(url_for('loyalty.challenges'))

    badges = LoyaltyBadge.query.filter_by(is_active=True).all()
    return render_template('loyalty/create_challenge.html', badges=badges)


@bp.route('/challenges/<int:challenge_id>/toggle', methods=['POST'])
@login_required
def toggle_challenge(challenge_id):
    """Toggle challenge active status"""
    if current_user.role not in ['admin', 'manager']:
        return jsonify({'success': False, 'error': 'Access denied'}), 403

    challenge = LoyaltyChallenge.query.get_or_404(challenge_id)
    challenge.is_active = not challenge.is_active
    db.session.commit()

    return jsonify({'success': True, 'is_active': challenge.is_active})


# Customer loyalty dashboard API
@bp.route('/customer/<int:customer_id>/dashboard')
@login_required
def customer_dashboard(customer_id):
    """Get customer loyalty dashboard data"""
    customer = Customer.query.get_or_404(customer_id)

    # Get customer badges
    customer_badges = db.session.query(LoyaltyBadge, CustomerBadge).join(
        CustomerBadge, CustomerBadge.badge_id == LoyaltyBadge.id
    ).filter(
        CustomerBadge.customer_id == customer_id
    ).all()

    badges = [{
        'id': b.LoyaltyBadge.id,
        'name': b.LoyaltyBadge.name,
        'description': b.LoyaltyBadge.description,
        'icon': b.LoyaltyBadge.icon,
        'color': b.LoyaltyBadge.color,
        'earned_at': b.CustomerBadge.earned_at.isoformat()
    } for b in customer_badges]

    # Get available badges customer doesn't have
    earned_badge_ids = [b.LoyaltyBadge.id for b in customer_badges]
    available_badges = LoyaltyBadge.query.filter(
        LoyaltyBadge.is_active == True,
        ~LoyaltyBadge.id.in_(earned_badge_ids) if earned_badge_ids else True
    ).all()

    available = [{
        'id': b.id,
        'name': b.name,
        'description': b.description,
        'icon': b.icon,
        'color': b.color,
        'criteria_type': b.criteria_type,
        'criteria_value': b.criteria_value
    } for b in available_badges]

    # Get active challenge progress
    active_challenges = db.session.query(LoyaltyChallenge, CustomerChallengeProgress).outerjoin(
        CustomerChallengeProgress,
        (CustomerChallengeProgress.challenge_id == LoyaltyChallenge.id) &
        (CustomerChallengeProgress.customer_id == customer_id)
    ).filter(
        LoyaltyChallenge.is_active == True,
        LoyaltyChallenge.start_date <= datetime.utcnow(),
        LoyaltyChallenge.end_date >= datetime.utcnow()
    ).all()

    challenges = [{
        'id': c.LoyaltyChallenge.id,
        'name': c.LoyaltyChallenge.name,
        'description': c.LoyaltyChallenge.description,
        'target_value': c.LoyaltyChallenge.target_value,
        'current_value': c.CustomerChallengeProgress.current_value if c.CustomerChallengeProgress else 0,
        'completed': c.CustomerChallengeProgress.completed if c.CustomerChallengeProgress else False,
        'reward_type': c.LoyaltyChallenge.reward_type,
        'reward_value': c.LoyaltyChallenge.reward_value,
        'end_date': c.LoyaltyChallenge.end_date.isoformat(),
        'progress_percent': min(100, int(((c.CustomerChallengeProgress.current_value if c.CustomerChallengeProgress else 0) / c.LoyaltyChallenge.target_value) * 100)) if c.LoyaltyChallenge.target_value > 0 else 0
    } for c in active_challenges]

    # Get referral info
    if not customer.referral_code:
        generate_referral_code(customer_id)
        customer = Customer.query.get(customer_id)

    referral_count = Referral.query.filter_by(
        referrer_id=customer_id,
        status='completed'
    ).count()

    # Calculate tier progress
    tier_thresholds = {
        'bronze': {'min': 0, 'max': 500, 'next': 'Silver'},
        'silver': {'min': 500, 'max': 2000, 'next': 'Gold'},
        'gold': {'min': 2000, 'max': 5000, 'next': 'Platinum'},
        'platinum': {'min': 5000, 'max': None, 'next': None}
    }

    current_tier = customer.loyalty_tier.lower() if customer.loyalty_tier else 'bronze'
    tier_info = tier_thresholds.get(current_tier, tier_thresholds['bronze'])

    if tier_info['max']:
        tier_progress = min(100, int(((customer.loyalty_points or 0) - tier_info['min']) / (tier_info['max'] - tier_info['min']) * 100))
        points_to_next = max(0, tier_info['max'] - (customer.loyalty_points or 0))
    else:
        tier_progress = 100
        points_to_next = 0

    return jsonify({
        'success': True,
        'customer': {
            'id': customer.id,
            'name': customer.name,
            'loyalty_points': customer.loyalty_points or 0,
            'loyalty_tier': customer.loyalty_tier or 'Bronze',
            'referral_code': customer.referral_code,
            'total_purchases': Sale.query.filter_by(customer_id=customer_id).count()
        },
        'tier_progress': {
            'current_tier': current_tier.title(),
            'next_tier': tier_info['next'],
            'progress_percent': tier_progress,
            'points_to_next': points_to_next
        },
        'badges': {
            'earned': badges,
            'available': available
        },
        'challenges': challenges,
        'referrals': {
            'code': customer.referral_code,
            'count': referral_count,
            'points_per_referral': 100
        }
    })


@bp.route('/check-badges/<int:customer_id>', methods=['POST'])
@login_required
def check_badges_endpoint(customer_id):
    """Manually check and award badges for a customer"""
    new_badges = check_and_award_badges(customer_id)
    return jsonify({
        'success': True,
        'new_badges': new_badges
    })


@bp.route('/referral/apply', methods=['POST'])
@login_required
def apply_referral():
    """Apply a referral code to a customer"""
    data = request.get_json()
    referral_code = data.get('referral_code')
    customer_id = data.get('customer_id')

    if not referral_code or not customer_id:
        return jsonify({'success': False, 'error': 'Missing referral code or customer ID'}), 400

    referral = process_referral(referral_code, customer_id)

    if referral:
        return jsonify({
            'success': True,
            'message': 'Referral applied successfully!',
            'referrer_reward': referral.referrer_reward,
            'referred_reward': referral.referred_reward
        })
    else:
        return jsonify({'success': False, 'error': 'Invalid referral code or already used'}), 400


@bp.route('/generate-referral-code/<int:customer_id>', methods=['POST'])
@login_required
def generate_code(customer_id):
    """Generate referral code for a customer"""
    code = generate_referral_code(customer_id)
    if code:
        return jsonify({'success': True, 'code': code})
    return jsonify({'success': False, 'error': 'Customer not found'}), 404
