from __future__ import annotations

import structlog
from grunt.core.tasks.broker import retryable_task
from grunt.core.email.service import EmailService
from grunt.core.site.manager import site_manager

from grunt.core.document.service import DocumentService
from grunt.core.auth.models import GruntUser

logger = structlog.get_logger()

# System user for email tasks
SYSTEM_USER = GruntUser(
    email="system@grunt.local",
    full_name="System",
    is_superadmin=True
)

@retryable_task()
async def process_email_queue():
    """Select Pending emails from EmailQueue and send them."""
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    eng = site_manager.get_engine(site)
    async with maker() as session:
        service = DocumentService(session, eng)
        
        # 1. Fetch Pending emails
        try:
            result = await service.list_documents(
                "EmailQueue", 
                SYSTEM_USER, 
                filters={"status": "Pending"},
                per_page=100
            )
            queue_items = result["data"]
            
            if not queue_items:
                return

            logger.info("email.processing_queue", count=len(queue_items))

            for item in queue_items:
                # 2. Get Account settings
                # Note: list_documents returns raw data. We need to fetch the account.
                account_id = item.get("email_account")
                if not account_id:
                    logger.warning("email.no_account_for_item", id=item["id"])
                    continue
                
                account = await service.get_document("EmailAccount", account_id, SYSTEM_USER)
                
                try:
                    # 3. Send
                    await EmailService.send_now(account, item)
                    
                    # 4. Update status
                    await service.update_document(
                        "EmailQueue", 
                        item["id"], 
                        {"status": "Sent"}, 
                        SYSTEM_USER
                    )
                    await session.commit()
                except Exception as e:
                    await service.update_document(
                        "EmailQueue", 
                        item["id"], 
                        {"status": "Error", "error_message": str(e)}, 
                        SYSTEM_USER
                    )
                    await session.commit()
                    
        except Exception as e:
            logger.error("email.queue_processing_failed", error=str(e))
            raise


@retryable_task()
async def pull_from_accounts():
    """Fetch emails from all active EmailAccounts."""
    site = site_manager.get_active_site()
    maker = site_manager.get_session_maker(site)
    eng = site_manager.get_engine(site)
    async with maker() as session:
        service = DocumentService(session, eng)
        
        try:
            result = await service.list_documents(
                "EmailAccount", 
                SYSTEM_USER, 
                filters={"enable_incoming": "True"}
            )
            accounts = result["data"]
            
            for account in accounts:
                emails = await EmailService.pull_emails(account)
                for email_data in emails:
                    # Trigger hook for inbound email
                    # Apps can register to this hook to create Support Tickets, Leads, etc.
                    from grunt.core.hooks import fire
                    await fire(
                        "inbound_email", 
                        account=account, 
                        email_data=email_data,
                        session=session,
                        user=SYSTEM_USER
                    )
                    await session.commit()
                    
        except Exception as e:
            logger.error("email.pull_from_accounts_failed", error=str(e))
            raise
