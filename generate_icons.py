import os
from PIL import Image, ImageDraw

def create_icon(size, output_path):
    img = Image.new('RGBA', (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    
    # SVG viewBox is 0 0 16 16
    # cx=8, cy=8, r=7, fill=#B2054C
    # Scale factor
    s = size / 16.0
    
    # Outer circle
    draw.ellipse([ (1)*s, (1)*s, (15)*s, (15)*s ], fill='#B2054C')
    
    # Middle stroke circle: cx=8, cy=8, r=4, stroke-width=1.6
    draw.ellipse([ (4)*s, (4)*s, (12)*s, (12)*s ], outline='#007DCC', width=int(1.6 * s))
    
    # Inner circle cx=8, cy=8, r=1.5
    draw.ellipse([ (6.5)*s, (6.5)*s, (9.5)*s, (9.5)*s ], fill='#FFB900')
    
    img.save(output_path)

if __name__ == '__main__':
    icons_dir = os.path.join('static', 'icons')
    os.makedirs(icons_dir, exist_ok=True)
    
    create_icon(192, os.path.join(icons_dir, 'icon-192x192.png'))
    create_icon(512, os.path.join(icons_dir, 'icon-512x512.png'))
    print("Icons generated successfully!")
