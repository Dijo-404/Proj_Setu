from types import SimpleNamespace

from app.templates import templates


def test_sale_new_batch_has_fallback_state_and_gst_options():
    html = templates.env.get_template("batch_new.html").render(
        user=None,
        batch_type=SimpleNamespace(value="SALE"),
        party_name="",
        party_state="",
        notes="",
        error=None,
    )

    assert 'name="party_state" list="sale-state-options"' in html
    assert 'name="party_state" list="sale-state-options" placeholder="State" value="Karnataka"' in html
    assert "Debtor ledger name" in html
    assert 'name="party_gst_registration_type"' in html
    assert '<option value="Unregistered/Consumer" selected>Unregistered/Consumer</option>' in html
    assert 'name="party_gst_name"' in html
    assert 'data-gst-number-field hidden' in html
    assert 'name="party_gstin"' in html
    assert "disabled" in html
    assert '<option value="Karnataka"></option>' in html
    assert 'name="gst_treatment"' not in html
    assert 'name="gst_cgst_rate" type="number"' in html
    assert 'name="gst_sgst_rate" type="number"' in html
    assert 'name="gst_igst_rate" type="number"' in html
    assert "IGST % (optional)" in html
    assert 'name="gst_igst_rate" type="number" min="0" max="100" step="0.01" placeholder="5" value="" required' not in html


def test_registered_sale_new_batch_shows_gst_number():
    html = templates.env.get_template("batch_new.html").render(
        user=None,
        batch_type=SimpleNamespace(value="SALE"),
        party_name="",
        party_state="",
        party_gst_registration_type="Regular",
        party_gst_name="",
        party_gstin="",
        notes="",
        error=None,
    )

    assert '<option value="Regular" selected>Registered</option>' in html
    assert 'name="party_state" list="sale-state-options" placeholder="State" value="Karnataka"' not in html
    assert 'data-gst-number-field hidden' not in html
    assert 'name="party_gst_name"' in html
    assert 'name="party_gstin"' in html
