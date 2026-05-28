from l2l3_protocol.workers.build_in_public_worker import adapt


def test_channel_adapter_accepts_real_hermes_atom_shape() -> None:
    result = adapt(
        {
            'inputs': {
                'atoms': [
                    {
                        'headline': 'Implemented evidence-backed review CLI',
                        'body': 'This allows checking claims against data directly from the terminal.',
                        'type': 'feature_update',
                    }
                ],
                'channels': ['x'],
            }
        },
        {},
    )

    assert result['drafts'][0]['channel'] == 'x'
    assert 'Implemented evidence-backed review CLI' in result['drafts'][0]['text']
    assert 'Why it matters' in result['drafts'][0]['text']
    assert result['drafts'][0]['source_angle'] == 'feature_update'


def test_channel_adapter_accepts_string_atoms() -> None:
    result = adapt(
        {
            'inputs': {
                'atoms': ['Implemented evidence-backed review CLI from the terminal.'],
                'channels': ['x'],
            }
        },
        {},
    )

    assert result['drafts'][0]['text'] == 'Implemented evidence-backed review CLI from the terminal.'
    assert result['drafts'][0]['source_angle'] == 'generic'
