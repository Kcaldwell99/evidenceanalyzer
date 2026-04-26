from app.c2pa_analysis import analyze_file, plain_english_findings

result = analyze_file(r"C:\Users\kcald\Pictures\test.jpg")
print(f"State:          {result.state.value}")
print(f"Error detail:   {result.error_detail}")   # ADD THIS LINE
print(f"Claim generator:{result.claim_generator}")
print(f"Sig valid:      {result.signature_valid}")
print(f"AI generated:   {result.has_ai_generation}")
print(f"AI modified:    {result.has_ai_modification}")
print(f"\nNarrative:\n{plain_english_findings(result)}")