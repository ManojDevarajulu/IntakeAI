.PHONY: test eval run synth

test:
	py tests/test_clinical_verifier.py
	py tests/test_schema_integrity.py
	py tests/test_synth_generator.py
	py tests/test_phase3_pipeline.py
	py tests/test_web_service.py

eval:
	py src/eval_runner.py

run:
	py run.py

synth:
	py -c "from src.synth_generator import SyntheticFaxGenerator; g = SyntheticFaxGenerator(); g.generate_sample_suite('data/referral_fixtures.json', 'data/generated')"
