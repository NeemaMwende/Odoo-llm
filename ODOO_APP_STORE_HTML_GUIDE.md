# Odoo App Store HTML Guide

## What We Learned About index.html for Odoo App Store

This guide documents the CSS patterns, HTML structure, and best practices for creating `index.html` files that work correctly in the Odoo App Store after sanitization.

---

## ✅ SAFE CSS PATTERNS (Proven to Work)

### Layout & Structure
- **Bootstrap 5 Grid**: `container`, `row`, `col-md-*`, `col-lg-*`, `col-xl-*`, `col-sm-*`, `col-12`
- **Flexbox**: `d-flex`, `align-items-center`, `justify-content-center`, `flex-md-row`, `flex-column`
- **Display**: `d-lg-none`, `d-flex`, `d-xl-block`, `d-none`

### Colors & Backgrounds
- **background-color with HEX colors**: ✅ WORKS on any element
  ```html
  <div style="background-color:#f8f9fa">...</div>
  <div style="background-color:#875A7B">...</div>
  <div style="background-color:#f5efff">...</div>
  ```
- Use hex colors only, NOT rgba()

### Spacing
- **Padding**: `p-2`, `px-0`, `py-3`, `px-md-5`, `px-4`, inline `padding:12px 15px`
- **Margin**: `mb-4`, `mt-5`, `mx-2`, `my-4`, `mx-auto`
- **Width/Height**: `w-100`, `h-100`, inline `width:98.5%`

### Typography
- **font-weight**: `font-weight:700`, `font-weight:600`, `font-weight:500`, `font-weight:400`
- **font-size**: `font-size:40px`, `font-size:16px`, `font-size:14px`
- **line-height**: `line-height:19px`, `line-height:25px`
- **color**: `color:#171618`, `color:#fff`, `color:#875A7B`
- **text-align**: `text-align:center`, `text-align:left`

### Borders & Radius
- **border**: `border:2px solid #acb7d5`, `border:none`
- **border-radius**: `border-radius:8px`, `border-radius:20px`, `border-radius:30px`
- **border-bottom**: `border-bottom:1px solid transparent`

### Other Safe Properties
- **text-decoration**: `text-decoration:none`
- **text-transform**: `text-transform:capitalize`
- **white-space**: `white-space:nowrap`
- **object-fit**: `object-fit:contain`

---

## ❌ AVOID THESE (Will Be Stripped or Cause Issues)

### 1. CSS Transitions and Transforms
```html
<!-- ❌ DON'T USE -->
<div style="transition:transform 0.3s">...</div>
<div style="transform:translateY(-5px)">...</div>
```
**Why**: Not used in published Odoo app store pages, likely stripped by sanitizer.

### 2. Inline JavaScript Event Handlers
```html
<!-- ❌ DON'T USE -->
<div onmouseover="this.style.transform='translateY(-5px)'" onmouseout="this.style.transform='translateY(0)'">
```
**Why**: Content Security Policy (CSP) restrictions and sanitization will remove these.

### 3. RGBA Colors
```html
<!-- ❌ DON'T USE -->
<div style="background-color:rgba(135,90,123,0.1)">...</div>

<!-- ✅ USE INSTEAD -->
<div style="background-color:#f5efff">...</div>
```
**Why**: Not used in published apps. Use hex color equivalents instead.

### 4. Linear Gradients
```html
<!-- ❌ DON'T USE -->
<div style="background:linear-gradient(to right, #875A7B, #acb7d5)">...</div>
```
**Why**: Gets stripped by Odoo's sanitizer.

### 5. Complex Box Shadows (Inline)
```html
<!-- ❌ DON'T USE -->
<div style="box-shadow:0 4px 6px rgba(0,0,0,0.1)">...</div>

<!-- ✅ USE INSTEAD -->
<div class="shadow-sm">...</div>
```
**Why**: Use Bootstrap's `shadow`, `shadow-sm`, `shadow-lg` classes instead.

### 6. Full HTML Document Structure
```html
<!-- ❌ DON'T USE -->
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>My App</title>
</head>
<body>
    <!-- content -->
</body>
</html>

<!-- ✅ USE INSTEAD -->
<section>
    <!-- content starts directly -->
</section>
```
**Why**: Odoo injects your HTML as a fragment into its own template. The wrapper will be ignored or cause issues.

---

## 🎨 RECOMMENDED PATTERNS

### Section Structure
```html
<section>
    <div class="container py-5">
        <div class="row justify-content-center">
            <div class="col-md-6 col-12">
                <h1 style="color:#875A7B; font-size:42px; font-weight:700">Title</h1>
                <p style="color:#666; font-size:16px">Description</p>
            </div>
        </div>
    </div>
</section>
```

### Colored Background Sections
```html
<section style="background-color:#f8f9fa">
    <div class="container py-5">
        <div class="row">
            <!-- content -->
        </div>
    </div>
</section>
```

### Cards with Background Colors
```html
<div class="col-md-4 col-12 mb-4">
    <div class="card h-100 shadow-sm" style="border:none; border-radius:12px">
        <div class="card-body p-4">
            <h3 style="color:#875A7B; font-weight:600">Card Title</h3>
            <p style="color:#666">Card content</p>
        </div>
    </div>
</div>
```

### Feature Cards with Custom Background
```html
<div class="col-md-3 col-sm-6 col-12 mb-4">
    <div class="card h-100" style="background-color:#f5efff; border:none; border-radius:12px">
        <div class="card-body p-4 text-center">
            <div class="mb-3" style="width:60px; height:60px; border-radius:50%; background-color:#875A7B">
                <i class="fa fa-check" style="color:#fff; font-size:24px"></i>
            </div>
            <h4 style="font-weight:600; color:#333">Feature</h4>
            <p style="color:#666">Description</p>
        </div>
    </div>
</div>
```

### Responsive Column Patterns
```html
<!-- 3 columns on desktop, 1 on mobile -->
<div class="col-md-4 col-12 mb-4">...</div>

<!-- 4 columns on desktop, 2 on tablet, 1 on mobile -->
<div class="col-md-3 col-sm-6 col-12 mb-4">...</div>

<!-- 6 columns on large screens, 4 on medium, 2 on mobile -->
<div class="col-lg-2 col-md-4 col-6 mb-4">...</div>
```

### Alert/Notice Boxes
```html
<div class="alert" style="background-color:#f5efff; border:2px solid #875A7B; border-radius:12px; padding:20px">
    <p style="color:#333; margin-bottom:0">
        <strong>Note:</strong> Important information here
    </p>
</div>
```

---

## 🎯 COLOR PALETTE (Safe Hex Colors)

### Primary Colors
- **Odoo Purple**: `#875A7B`
- **White**: `#fff` or `#ffffff`
- **Black/Dark Gray**: `#333` or `#171618`
- **Medium Gray**: `#666`

### Background Colors
- **Very Light Gray**: `#f8f9fa`
- **Light Purple Tint**: `#f5efff`
- **Lighter Purple Tint**: `#f7f2fa`
- **Very Subtle Purple**: `#faf8fc`
- **White**: `#fff`

### Accent Colors
- **Light Blue**: `#acb7d5`
- **Dark Gray**: `#2d3748`

---

## 📱 RESPONSIVE DESIGN

### Breakpoints (Bootstrap 5)
- **col-12**: Mobile (< 576px) - always full width
- **col-sm-***: Small tablets (≥ 576px)
- **col-md-***: Tablets (≥ 768px)
- **col-lg-***: Desktops (≥ 992px)
- **col-xl-***: Large desktops (≥ 1200px)

### Common Responsive Patterns
```html
<!-- Stack on mobile, 2 columns on tablet, 3 on desktop -->
<div class="row">
    <div class="col-md-4 col-sm-6 col-12">...</div>
    <div class="col-md-4 col-sm-6 col-12">...</div>
    <div class="col-md-4 col-sm-6 col-12">...</div>
</div>

<!-- Hide on mobile, show on desktop -->
<div class="d-none d-md-block">...</div>

<!-- Show on mobile, hide on desktop -->
<div class="d-block d-md-none">...</div>
```

---

## 🔧 DEVELOPMENT WORKFLOW

### 1. Reference Analysis
Always analyze published Odoo app store pages first:
- Look at `detailed.html` from successful apps
- Document CSS patterns used
- Note what's NOT used (likely stripped)

### 2. HTML Structure
- Start directly with `<section>` tags
- No `<!DOCTYPE>`, `<html>`, `<head>`, or `<body>`
- Use Bootstrap 5 grid system exclusively
- Structure: `section → container → row → col-*`

### 3. Styling Approach
- Use Bootstrap utility classes for spacing, layout, display
- Use inline styles for colors, typography, borders
- Stick to hex colors only
- No animations, transitions, or transforms

### 4. Testing Checklist
- [ ] No DOCTYPE, html, head, body tags
- [ ] No rgba() colors - only hex
- [ ] No transitions or transforms
- [ ] No inline JavaScript (onclick, onmouseover, etc.)
- [ ] No linear-gradients
- [ ] Bootstrap classes for layout
- [ ] Inline styles for colors/typography
- [ ] Responsive column patterns used
- [ ] All sections have proper spacing

---

## 📚 REFERENCE FILES

### Source of Truth
- **llm_mcp_server/static/description/detailed.html** - Published Odoo app with proven CSS patterns
- **llm_mcp_server/static/description/index.html** - Our production-ready file

### Analysis Documents
- **llm_mcp_server/static/description/css_analysis.md** - Comprehensive CSS pattern analysis

---

## 🚀 QUICK START TEMPLATE

```html
<!-- Hero Section -->
<section>
    <div class="container py-5">
        <div class="row justify-content-center">
            <div class="col-md-8 col-12 text-center">
                <h1 style="color:#875A7B; font-size:42px; font-weight:700; margin-bottom:20px">
                    Your App Name
                </h1>
                <p style="color:#666; font-size:18px; line-height:28px">
                    Brief description of your module
                </p>
            </div>
        </div>
    </div>
</section>

<!-- Features Section -->
<section style="background-color:#f8f9fa">
    <div class="container py-5">
        <div class="row">
            <div class="col-12 text-center mb-4">
                <h2 style="color:#875A7B; font-size:32px; font-weight:700">Features</h2>
            </div>
        </div>
        <div class="row">
            <div class="col-md-4 col-12 mb-4">
                <div class="card h-100 shadow-sm" style="border:none; border-radius:12px">
                    <div class="card-body p-4 text-center">
                        <div class="mb-3 d-inline-flex align-items-center justify-content-center"
                             style="width:60px; height:60px; border-radius:50%; background-color:#f5efff">
                            <i class="fa fa-check" style="color:#875A7B; font-size:24px"></i>
                        </div>
                        <h3 style="color:#333; font-size:20px; font-weight:600; margin-bottom:15px">
                            Feature 1
                        </h3>
                        <p style="color:#666; font-size:14px; line-height:22px">
                            Feature description
                        </p>
                    </div>
                </div>
            </div>
            <!-- Repeat for more features -->
        </div>
    </div>
</section>

<!-- Footer -->
<section>
    <div class="container py-5">
        <div class="row justify-content-center">
            <div class="col-md-6 col-12 text-center">
                <h3 style="color:#875A7B; font-size:24px; font-weight:600; margin-bottom:20px">
                    Get Support
                </h3>
                <p style="color:#666; font-size:16px; margin-bottom:30px">
                    Need help? Contact us:
                </p>
                <a href="mailto:support@example.com"
                   class="btn btn-primary"
                   style="background-color:#875A7B; border:none; border-radius:8px; padding:12px 30px">
                    Contact Support
                </a>
            </div>
        </div>
    </div>
</section>
```

---

## ⚠️ COMMON MISTAKES TO AVOID

1. **Using full HTML document structure** - Start directly with `<section>`
2. **Using rgba() colors** - Convert to hex equivalents
3. **Adding hover effects with JavaScript** - Not supported
4. **Using CSS transitions** - Will be stripped
5. **Complex CSS in inline styles** - Keep it simple
6. **Forgetting responsive classes** - Always add `col-12` for mobile
7. **Using gradients** - Use solid colors only
8. **Inline box-shadow** - Use Bootstrap `shadow` classes

---

## 📊 VALIDATION CHECKLIST

Before submitting to Odoo App Store:

- [ ] File starts with `<section>` or comment, NOT `<!DOCTYPE>`
- [ ] All colors are hex format (#xxxxxx), no rgba()
- [ ] No CSS transitions, transforms, or animations
- [ ] No inline JavaScript handlers (onclick, onmouseover, etc.)
- [ ] Using Bootstrap 5 grid classes (container, row, col-*)
- [ ] All sections have responsive column patterns
- [ ] Bootstrap utility classes used for spacing (p-*, m-*, mb-*)
- [ ] Card components use `h-100` for equal heights
- [ ] Text uses inline styles for colors and typography
- [ ] Icons use FontAwesome classes (fa, fa-*)
- [ ] All sections tested for mobile responsiveness

---

## 📝 NOTES

- **Bootstrap Version**: Odoo uses Bootstrap 5 in newer versions
- **FontAwesome**: Available for icons (use `fa` class prefix)
- **Sanitization**: Odoo strips potentially dangerous HTML/CSS/JS
- **Fragment Injection**: Your HTML is injected into Odoo's template as a fragment
- **No Custom CSS Files**: Can't link external stylesheets, use inline styles
- **No Custom JavaScript**: No way to add custom JS, must work with static HTML
