with open('app/templates/upload.html', 'r', encoding='utf-8') as f:
    content = f.read()

new_grid = '''                <div class="pricing-grid">
                    <div class="price-card">
                        <h3>Single Report</h3>
                        <h2>$79</h2>
                        <p>Per analysis</p>
                        <p>PDF report included</p>
                        <a href="/checkout/single" class="button">Buy Now</a>
                    </div>

                    <div class="price-card">
                        <h3>Case Bundle</h3>
                        <h2>$299</h2>
                        <p>Up to 10 analyses</p>
                        <p>PDF reports included</p>
                        <a href="/checkout/bundle" class="button">Buy Now</a>
                    </div>

                    <div class="price-card">
                        <h3>Professional</h3>
                        <h2>$399/mo</h2>
                        <p>Up to 150 analyses</p>
                        <p>Unlimited cases</p>
                        <a href="/checkout/professional" class="button">Buy Now</a>
                    </div>

                    <div class="price-card featured">
                        <h3>Firm License</h3>
                        <h2>$7,500/yr</h2>
                        <p>Unlimited analyses</p>
                        <p>Unlimited reports</p>
                        <a href="/checkout/firm" class="button">Buy Now</a>
                    </div>
                </div>'''

# Find start of pricing-grid
start = content.find('<div class="pricing-grid">')
if start == -1:
    print("ERROR: pricing-grid not found")
    exit(1)

# Find the closing </div> of the pricing-grid
# Count nested divs to find the matching close
pos = start
depth = 0
end = -1
while pos < len(content):
    if content[pos:pos+4] == '<div':
        depth += 1
        pos += 4
    elif content[pos:pos+6] == '</div>':
        depth -= 1
        if depth == 0:
            end = pos + 6
            break
        pos += 6
    else:
        pos += 1

if end == -1:
    print("ERROR: Could not find closing div")
    exit(1)

new_content = content[:start] + new_grid + content[end:]

with open('app/templates/upload.html', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("SUCCESS - pricing grid replaced")
print(f"Grid ran from char {start} to {end}")
