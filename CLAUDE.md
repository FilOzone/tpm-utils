# Repository Conventions

This document outlines the conventions and best practices for the FilOz TPM Utils repository.

## Commit Message Format

This repository uses [Conventional Commits](https://www.conventionalcommits.org/) for all commit messages.

### Format

```
<type>: <description>

[optional body]

[optional footer(s)]
```

### Types

- **feat**: New features or functionality
- **fix**: Bug fixes
- **docs**: Documentation changes
- **refactor**: Code refactoring without changing functionality
- **perf**: Performance improvements
- **test**: Adding or updating tests
- **chore**: Maintenance tasks, dependency updates
- **ci**: CI/CD configuration changes
- **style**: Code style changes (formatting, whitespace)

### Examples

```
feat: add configurable delay between search queries

docs: add filtering chain list messages from Slack search results

refactor: implement two-phase workflow with JSON export/import

fix: resolve hanging issue with large repositories
```

## File Organization

### Documentation Files

- `README.md` - Main repository overview and navigation
- `CLAUDE.md` - Repository conventions and guidelines (this file)
- `*.md` - Tool-specific documentation files with descriptive names

### Python Scripts

- Use descriptive names that indicate purpose
- Include docstrings and type hints where appropriate
- Follow PEP 8 style guidelines

### Naming Conventions

- **Files**: Use descriptive names with underscores for Python scripts
- **Documentation**: Use UPPER_CASE with descriptive names for markdown files
- **Directories**: Use lowercase with hyphens if needed

## Development Workflow

### Before Committing

1. **Review changes**: Ensure all changes are intentional and complete
2. **Test functionality**: Verify scripts work as expected
3. **Update documentation**: Keep docs in sync with code changes
4. **Use conventional commits**: Format commit messages properly

### Documentation Standards

- Keep documentation up-to-date with code changes
- Use clear, concise language
- Include practical examples and command sequences
- Link between related documents using relative paths

## Tool-Specific Guidelines

### Python Scripts

- Use `python3` in all examples and shebang lines
- Include proper error handling
- Use environment variables for sensitive data (tokens, etc.)
- Provide helpful command-line interfaces with `--help` options

### Markdown Documentation

- Use relative links for internal references
- Include code examples with proper syntax highlighting
- Structure content with clear headings and sections
- Provide both quick start and detailed usage examples

## Quality Standards

### Code Quality

- Scripts should be robust and handle edge cases
- Include appropriate error messages and logging
- Use meaningful variable and function names
- Comment complex logic or regex patterns

### Documentation Quality

- Keep examples current and working
- Provide context for when/why to use each tool
- Include troubleshooting sections where helpful
- Maintain consistent formatting and style

## Contributing

When contributing to this repository:

1. Follow all conventions outlined in this document
2. Update relevant documentation for any changes
3. Use conventional commit messages
4. Test changes thoroughly before submitting
5. Keep the scope of changes focused and atomic

## Maintenance

### Regular Tasks

- Update dependency versions as needed
- Review and update documentation for accuracy
- Ensure all examples and commands still work
- Clean up obsolete files or references

### Git History

- Maintain clean commit history using conventional commits
- Use interactive rebase to clean up commits before pushing
- Avoid force-pushing to shared branches unless necessary
- Keep commit messages informative and professional

---

*This document should be updated as the repository evolves and new conventions are established.*