from app.c2pa_analysis import analyze_file, plain_english_findings

test_files = [
    r"C:\Users\kcald\Pictures\test.jpg",
]

for path in test_files:
    print(f"\n--- {path} ---")
    result = analyze_file(path)
    print(f"State:          {result.state.value}")
    print(f"Claim generator:{result.claim_generator}")
    print(f"Sig valid:      {result.signature_valid}")
    print(f"Trust status:   {result.trust_list_status}")
    print(f"Revocation:     {result.revocation_status}")
    print(f"AI generated:   {result.has_ai_generation}")
    print(f"AI modified:    {result.has_ai_modification}")
    print(f"\nNarrative:\n{plain_english_findings(result)}")