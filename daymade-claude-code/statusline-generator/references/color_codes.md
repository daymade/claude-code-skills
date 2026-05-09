# ANSI Color Codes Reference

This reference provides ANSI escape codes for customizing statusline colors.

## Format

ANSI color codes follow this format:
```
\033[<attributes>m<text>\033[00m
```

- `\033[` - Escape sequence start
- `<attributes>` - Color and style codes (see below)
- `m` - Marks end of escape sequence
- `\033[00m` - Reset to default

## Common Color Codes

### Regular Colors
- `\033[00;30m` - Black
- `\033[00;31m` - Red
- `\033[00;32m` - Green
- `\033[00;33m` - Yellow
- `\033[00;34m` - Blue
- `\033[00;35m` - Magenta
- `\033[00;36m` - Cyan
- `\033[00;37m` - White

### Bright/Bold Colors (Used in Default Statusline)
- `\033[01;30m` - Bright Black (Gray)
- `\033[01;31m` - Bright Red
- `\033[01;32m` - Bright Green
- `\033[01;33m` - Bright Yellow
- `\033[01;34m` - Bright Blue
- `\033[01;35m` - Bright Magenta
- `\033[01;36m` - Bright Cyan
- `\033[01;37m` - Bright White

## Default Statusline Colors

The generated statusline uses these colors by default:

| Element | Color Code | Color Name | Visibility |
|---------|-----------|------------|-----------|
| Username | `\033[01;32m` | Bright Green | Excellent |
| Model | `\033[01;36m` | Bright Cyan | Excellent |
| Costs | `\033[01;35m` | Bright Magenta | Excellent |
| Path | `\033[01;37m` | Bright White | Excellent |
| Git (clean) | `\033[01;33m` | Bright Yellow | Excellent |
| Git (dirty) | `\033[01;31m` | Bright Red | Excellent |

## Customizing Colors

To customize colors in the statusline script, edit the `printf` statements:

### Example: Change username to bright blue
```bash
# Original:
printf '\033[01;32m%s\033[00m' "$username"

# Modified:
printf '\033[01;34m%s\033[00m' "$username"
```

### Example: Change path to yellow
```bash
# Original:
printf '\033[01;37m%s\033[00m' "$short_path"

# Modified:
printf '\033[01;33m%s\033[00m' "$short_path"
```

## Testing Colors

Test color codes in terminal:
```bash
echo -e "\033[01;32mGreen\033[00m \033[01;36mCyan\033[00m \033[01;35mMagenta\033[00m"
```

## Tips

1. **Always reset**: End each colored section with `\033[00m` to reset colors
2. **Visibility**: Bright colors (01;3X) are more visible than regular (00;3X)
3. **Contrast**: Choose colors that contrast well with your terminal background
4. **Consistency**: Use consistent colors for similar elements across your environment