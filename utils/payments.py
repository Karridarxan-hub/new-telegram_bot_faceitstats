"""Telegram Stars payment integration."""

import logging
from typing import Dict, Any, Optional
from aiogram import Bot
from aiogram.types import PreCheckoutQuery, SuccessfulPayment, LabeledPrice

from utils.subscription import SubscriptionManager
from utils.storage import storage, SubscriptionTier

logger = logging.getLogger(__name__)


class PaymentManager:
    """Manages Telegram Stars payments for subscriptions."""
    
    def __init__(self, bot: Bot):
        self.bot = bot
    
    async def create_invoice(
        self, 
        user_id: int, 
        tier: SubscriptionTier, 
        duration: str = "monthly"
    ) -> Dict[str, Any]:
        """Create payment invoice for subscription using Telegram Stars."""
        try:
            # Get invoice data from subscription manager
            invoice_data = await SubscriptionManager.create_payment_invoice(user_id, tier, duration)
            
            # Create LabeledPrice for Telegram Stars
            prices = [
                LabeledPrice(
                    label=invoice_data["title"],
                    amount=invoice_data["prices"][0]["amount"]
                )
            ]
            
            # Send invoice to user
            await self.bot.send_invoice(
                chat_id=user_id,
                title=invoice_data["title"],
                description=invoice_data["description"],
                payload=invoice_data["payload"],
                provider_token="",  # Empty for Telegram Stars
                currency="XTR",  # Telegram Stars currency
                prices=prices,
                max_tip_amount=0,
                suggested_tip_amounts=[],
                start_parameter=f"pay_{tier.value}_{duration}",
                provider_data=None,
                photo_url=None,
                photo_size=None,
                photo_width=None,
                photo_height=None,
                need_name=False,
                need_phone_number=False,
                need_email=False,
                need_shipping_address=False,
                send_phone_number_to_provider=False,
                send_email_to_provider=False,
                is_flexible=False
            )
            
            logger.info(f"Invoice sent to user {user_id} for {tier.value} {duration}")
            return {"success": True, "invoice_data": invoice_data}
            
        except Exception as e:
            logger.error(f"Error creating invoice for user {user_id}: {e}")
            return {"success": False, "error": str(e)}
    
    async def handle_pre_checkout_query(self, pre_checkout_query: PreCheckoutQuery) -> bool:
        """Handle pre-checkout query (validate payment before processing)."""
        try:
            # Parse payload to validate
            payload = pre_checkout_query.invoice_payload
            parts = payload.split("_")
            
            if len(parts) != 3:
                logger.error(f"Invalid payload format: {payload}")
                await pre_checkout_query.answer(
                    ok=False, 
                    error_message="Ошибка в данных платежа. Попробуйте еще раз."
                )
                return False
            
            tier_str, duration, user_id_str = parts
            
            # Validate tier
            try:
                tier = SubscriptionTier(tier_str)
            except ValueError:
                logger.error(f"Invalid tier in payload: {tier_str}")
                await pre_checkout_query.answer(
                    ok=False,
                    error_message="Неверный тип подписки. Попробуйте еще раз."
                )
                return False
            
            # Validate user ID
            try:
                user_id = int(user_id_str)
                if user_id != pre_checkout_query.from_user.id:
                    logger.error(f"User ID mismatch: {user_id} vs {pre_checkout_query.from_user.id}")
                    await pre_checkout_query.answer(
                        ok=False,
                        error_message="Ошибка авторизации. Попробуйте еще раз."
                    )
                    return False
            except ValueError:
                logger.error(f"Invalid user ID in payload: {user_id_str}")
                await pre_checkout_query.answer(
                    ok=False,
                    error_message="Ошибка в данных пользователя. Попробуйте еще раз."
                )
                return False
            
            # Validate duration
            if duration not in ["monthly", "yearly"]:
                logger.error(f"Invalid duration in payload: {duration}")
                await pre_checkout_query.answer(
                    ok=False,
                    error_message="Неверная длительность подписки. Попробуйте еще раз."
                )
                return False
            
            # All validations passed
            await pre_checkout_query.answer(ok=True)
            logger.info(f"Pre-checkout validated for user {user_id}, {tier.value} {duration}")
            return True
            
        except Exception as e:
            logger.error(f"Error in pre-checkout handler: {e}")
            await pre_checkout_query.answer(
                ok=False,
                error_message="Произошла ошибка при обработке платежа. Попробуйте позже."
            )
            return False
    
    async def handle_successful_payment(self, user_id: int, payment: SuccessfulPayment) -> bool:
        """Handle successful payment and upgrade user subscription."""
        try:
            # Process payment through subscription manager
            success = await SubscriptionManager.process_successful_payment(
                user_id=user_id,
                payload=payment.invoice_payload,
                telegram_payment_charge_id=payment.telegram_payment_charge_id
            )
            
            if success:
                # Send confirmation message to user
                await self._send_payment_confirmation(user_id, payment)
                logger.info(f"Payment processed successfully for user {user_id}")
            else:
                # Send error message
                await self._send_payment_error(user_id)
                logger.error(f"Failed to process payment for user {user_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error handling successful payment for user {user_id}: {e}")
            await self._send_payment_error(user_id)
            return False
    
    async def _send_payment_confirmation(self, user_id: int, payment: SuccessfulPayment):
        """Send payment confirmation message to user."""
        try:
            # Parse payment info
            parts = payment.invoice_payload.split("_")
            tier_str, duration, _ = parts
            tier = SubscriptionTier(tier_str)
            
            # Get user's new subscription status
            status_message = await SubscriptionManager.format_subscription_status(user_id)
            
            confirmation_message = "🎉 <b>Платеж успешно обработан!</b>\n\n"
            confirmation_message += f"💎 <b>Подписка:</b> {tier.value.title()}\n"
            confirmation_message += f"⏰ <b>Период:</b> {'месяц' if duration == 'monthly' else 'год'}\n"
            confirmation_message += f"💰 <b>Сумма:</b> {payment.total_amount} ⭐\n\n"
            confirmation_message += "Ваша новая подписка уже активна!\n\n"
            confirmation_message += status_message
            
            await self.bot.send_message(
                chat_id=user_id,
                text=confirmation_message,
                parse_mode="HTML"
            )
            
        except Exception as e:
            logger.error(f"Error sending payment confirmation: {e}")
    
    async def _send_payment_error(self, user_id: int):
        """Send payment error message to user."""
        try:
            error_message = "❌ <b>Ошибка при обработке платежа</b>\n\n"
            error_message += "Произошла ошибка при активации подписки. "
            error_message += "Если средства были списаны, подписка будет активирована автоматически в течение нескольких минут.\n\n"
            error_message += "Если проблема сохраняется, обратитесь в поддержку."
            
            await self.bot.send_message(
                chat_id=user_id,
                text=error_message,
                parse_mode="HTML"
            )
            
        except Exception as e:
            logger.error(f"Error sending payment error message: {e}")
    
    async def handle_payment_refund(self, user_id: int, refund_amount: int, reason: str = None):
        """Handle payment refund (for admin use)."""
        try:
            # Downgrade user subscription
            user = await storage.get_user(user_id)
            if user:
                user.subscription.tier = SubscriptionTier.FREE
                user.subscription.expires_at = None
                user.subscription.auto_renew = False
                await storage.save_user(user)
            
            # Send refund notification
            refund_message = "💸 <b>Возврат средств</b>\n\n"
            refund_message += f"💰 <b>Сумма:</b> {refund_amount} ⭐\n"
            if reason:
                refund_message += f"📝 <b>Причина:</b> {reason}\n"
            refund_message += "\nВаша подписка была отменена. Средства будут возвращены в течение 7-14 рабочих дней."
            
            await self.bot.send_message(
                chat_id=user_id,
                text=refund_message,
                parse_mode="HTML"
            )
            
            logger.info(f"Refund processed for user {user_id}: {refund_amount} stars")
            
        except Exception as e:
            logger.error(f"Error processing refund for user {user_id}: {e}")
    
    async def get_payment_statistics(self) -> Dict[str, Any]:
        """Get payment statistics for analytics."""
        try:
            subscription_stats = await storage.get_subscription_stats()
            
            # Calculate revenue estimates
            monthly_revenue_stars = (
                subscription_stats["premium_users"] * 199 +
                subscription_stats["pro_users"] * 299
            )
            
            yearly_revenue_stars = (
                subscription_stats["premium_users"] * 1999 +
                subscription_stats["pro_users"] * 2999
            ) // 12  # Approximate monthly from yearly subscriptions
            
            total_revenue_stars = monthly_revenue_stars + yearly_revenue_stars
            
            return {
                "total_revenue_stars": total_revenue_stars,
                "total_revenue_usd": total_revenue_stars * 0.1,  # Approximate conversion
                "monthly_subscribers": subscription_stats["premium_users"] + subscription_stats["pro_users"],
                "premium_revenue": subscription_stats["premium_users"] * 199,
                "pro_revenue": subscription_stats["pro_users"] * 299,
                "conversion_rate": round(
                    (subscription_stats["premium_users"] + subscription_stats["pro_users"]) /
                    max(subscription_stats["total_users"], 1) * 100, 2
                )
            }
            
        except Exception as e:
            logger.error(f"Error getting payment statistics: {e}")
            return {"error": str(e)}


# Helper functions for payment validation
def validate_payment_amount(tier: SubscriptionTier, duration: str, amount: int) -> bool:
    """Validate payment amount matches expected price."""
    expected_prices = {
        SubscriptionTier.PREMIUM: {"monthly": 199, "yearly": 1999},
        SubscriptionTier.PRO: {"monthly": 299, "yearly": 2999}
    }
    
    if tier not in expected_prices or duration not in expected_prices[tier]:
        return False
    
    return amount == expected_prices[tier][duration]


def format_payment_description(tier: SubscriptionTier, duration: str) -> str:
    """Format payment description for invoice."""
    tier_names = {
        SubscriptionTier.PREMIUM: "Premium",
        SubscriptionTier.PRO: "Pro"
    }
    
    duration_names = {
        "monthly": "на месяц",
        "yearly": "на год"
    }
    
    return f"Подписка {tier_names[tier]} {duration_names[duration]} для FACEIT Stats Bot"