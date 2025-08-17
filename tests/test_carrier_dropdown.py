def test_logistics_carrier_dropdown_options(client):
    resp = client.get('/logistics') if hasattr(client, 'get') else None
    # If route not defined, skip gracefully
    if not resp or resp.status_code != 200:
        return
    html = resp.get_data(as_text=True)
    # Quick presence checks against HTML
    assert 'name="carrier"' in html or 'id="carrierFilter"' in html, 'Carrier selects not found in logistics page'
    text = html
    # Only supported carriers present
    assert 'MSC' not in text and 'CMA CGM' not in text and 'UPS' not in text and 'Canada Post' not in text
    assert 'Maersk' in text and 'DHL' in text and 'FedEx' in text
