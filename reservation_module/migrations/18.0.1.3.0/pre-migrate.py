# -*- coding: utf-8 -*-

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Pre-migration: Remove deleted models/fields before ORM loads."""
    if not version:
        return

    _logger.info("Pre-migration 18.0.1.3.0: Removing appointment.answer, appointment.question.option, and obsolete fields")

    # Drop appointment_answer table and its relations
    cr.execute("DROP TABLE IF EXISTS appointment_answer_option_rel CASCADE")
    cr.execute("DROP TABLE IF EXISTS appointment_answer CASCADE")

    # Drop appointment_question_option table
    cr.execute("DROP TABLE IF EXISTS appointment_question_option CASCADE")

    # Remove obsolete columns from appointment_question
    for col in ('question_type', 'required', 'placeholder', 'help_text'):
        cr.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'appointment_question' AND column_name = %s
        """, (col,))
        if cr.fetchone():
            cr.execute(f"ALTER TABLE appointment_question DROP COLUMN {col}")
            _logger.info("Dropped column appointment_question.%s", col)

    # Add answer column to appointment_question if not exists
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'appointment_question' AND column_name = 'answer'
    """)
    if not cr.fetchone():
        cr.execute("ALTER TABLE appointment_question ADD COLUMN answer text")
        _logger.info("Added column appointment_question.answer")

    # Remove allow_invitations from appointment_type
    cr.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'appointment_type' AND column_name = 'allow_invitations'
    """)
    if cr.fetchone():
        cr.execute("ALTER TABLE appointment_type DROP COLUMN allow_invitations")
        _logger.info("Dropped column appointment_type.allow_invitations")

    # Remove answer_ids (One2many) doesn't need column drop - it's on the other side
    # But remove the booking_id column reference from appointment_answer (already dropped above)

    # Clean up ir.model.data references for deleted models
    cr.execute("""
        DELETE FROM ir_model_data
        WHERE model IN ('appointment.answer', 'appointment.question.option')
    """)

    # Clean up ir.model records
    cr.execute("""
        DELETE FROM ir_model
        WHERE model IN ('appointment.answer', 'appointment.question.option')
    """)

    # Clean up ir.model.fields for removed fields
    cr.execute("""
        DELETE FROM ir_model_fields
        WHERE model = 'appointment.type' AND name = 'allow_invitations'
    """)
    cr.execute("""
        DELETE FROM ir_model_fields
        WHERE model = 'appointment.booking' AND name = 'answer_ids'
    """)
    cr.execute("""
        DELETE FROM ir_model_fields
        WHERE model = 'appointment.question' AND name IN ('question_type', 'required', 'placeholder', 'help_text', 'option_ids')
    """)
    cr.execute("""
        DELETE FROM ir_model_fields
        WHERE model IN ('appointment.answer', 'appointment.question.option')
    """)

    # Clean up ir.model.access for deleted models
    cr.execute("""
        DELETE FROM ir_model_access
        WHERE name LIKE '%appointment.answer%' OR name LIKE '%appointment.question.option%'
    """)

    _logger.info("Pre-migration 18.0.1.3.0 completed successfully")
