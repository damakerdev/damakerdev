#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-PolyForm-Noncommercial-1.0.0
# Copyright (c) 2026 Isaac Adjei <https://isaacadjei.me>
#
# Profile generator tailored for damakerdev (the-maker-dev)
"""
profile.py — GitHub profile README SVG generator.

Generates three SVG cards (profile.svg, profile-dark.svg, and profile-light.svg):
  - profile.svg: theme-adaptive card (dark palette by default, light under prefers-color-scheme)
  - profile-dark.svg: fixed dark-mode card for <picture> source tags
  - profile-light.svg: fixed light-mode card for <picture> source tags
  - Left column: ASCII art portrait (44 cols x 30 rows, loaded from ascii_profile.txt)
  - Right column: neofetch-style info block + live GitHub stats pulled from the API

To run locally:
    export ACCESS_TOKEN=<fine-grained-PAT>
    python profile.py
"""

import os
import sys
import datetime
import requests
from dateutil.relativedelta import relativedelta
from html import escape as esc

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

USERNAME       = 'damakerdev'  # GitHub username to query

ASCII_ART_PATH = os.path.join(os.path.dirname(__file__), 'assets', 'ascii_profile.txt')
GRAPHQL_URL    = 'https://api.github.com/graphql'

ASCII_ROWS = 30
SVG_WIDTH  = 1120
ROW_STEP   = 20
ROW_START  = 30
LINE_WIDTH = 70

ASCII_X = 35
STATS_X = 410
ASCII_FONT_SIZE = 13
ASCII_Y_OFFSET = ROW_STEP

STATS_ROWS = 38
SVG_HEIGHT = ROW_START + (STATS_ROWS - 1) * ROW_STEP + ROW_STEP + 20

# ---------------------------------------------------------------------------
# Colour schemes
# ---------------------------------------------------------------------------

DARK = {
    'bg':     '#161b22',
    'text':   '#c9d1d9',
    'key':    '#ffa657',
    'value':  '#a5d6ff',
    'add':    '#3fb950',
    'delete': '#f85149',
    'dots':   '#616e7f',
}

LIGHT = {
    'bg':     '#f6f8fa',
    'text':   '#24292f',
    'key':    '#953800',
    'value':  '#0a3069',
    'add':    '#1a7f37',
    'delete': '#cf222e',
    'dots':   '#c2cfde',
}

# ---------------------------------------------------------------------------
# ASCII art loader
# ---------------------------------------------------------------------------

def load_ascii_art(path: str) -> list[str]:
    """Return ASCII_ROWS strings of 44 chars each from ascii_profile.txt."""
    if not os.path.exists(path):
        # Fallback if ascii_profile.txt doesn't exist yet
        return [" " * 44 for _ in range(ASCII_ROWS)]
    
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.read().splitlines()
    result = []
    for i in range(ASCII_ROWS):
        line = lines[i] if i < len(lines) else ''
        result.append(line.ljust(44)[:44])
    return result

# ---------------------------------------------------------------------------
# GitHub API helpers
# ---------------------------------------------------------------------------

def graphql(token: str, query: str, variables: dict | None = None) -> dict:
    headers = {'Authorization': f'bearer {token}', 'Content-Type': 'application/json'}
    resp = requests.post(GRAPHQL_URL,
                         json={'query': query, 'variables': variables or {}},
                         headers=headers, timeout=30)
    resp.raise_for_status()
    result = resp.json()
    if 'errors' in result:
        raise RuntimeError(f'GraphQL errors: {result["errors"]}')
    return result.get('data', {})


def get_user_info(token: str, username: str) -> tuple[int, int, int, int, int, int, str]:
    data = graphql(token, """
        query ($login: String!) {
            user(login: $login) {
                followers { totalCount }
                pullRequests { totalCount }
                issues { totalCount }
                gists(first: 1, privacy: PUBLIC) { totalCount }
                repositoriesContributedTo(
                    first: 1
                    contributionTypes: [COMMIT, PULL_REQUEST, PULL_REQUEST_REVIEW, ISSUE, REPOSITORY]
                    includeUserRepositories: true
                ) { totalCount }
                createdAt
            }
        }""", {'login': username})
    u = data.get('user', {})
    created_at = u.get('createdAt', '2022-01-01T00:00:00Z')
    return (
        u.get('followers',                   {}).get('totalCount', 0),
        u.get('pullRequests',                {}).get('totalCount', 0),
        u.get('repositoriesContributedTo',   {}).get('totalCount', 0),
        u.get('issues',                      {}).get('totalCount', 0),
        u.get('gists',                       {}).get('totalCount', 0),
        int(created_at[:4]),
        created_at,
    )


def get_repos_stars_and_forks(token: str, username: str) -> tuple[int, int, int]:
    query = """
        query ($login: String!, $cursor: String) {
            user(login: $login) {
                repositories(first: 100, after: $cursor, ownerAffiliations: OWNER,
                             orderBy: {field: UPDATED_AT, direction: DESC}) {
                    nodes { stargazerCount forkCount }
                    pageInfo { hasNextPage endCursor }
                    totalCount
                }
            }
        }"""
    stars, forks, total, cursor, first = 0, 0, 0, None, True
    while True:
        r = graphql(token, query, {'login': username, 'cursor': cursor})
        r = r.get('user', {}).get('repositories', {})
        if first:
            total, first = r.get('totalCount', 0), False
        stars += sum(n.get('stargazerCount', 0) for n in r.get('nodes', []))
        forks += sum(n.get('forkCount', 0) for n in r.get('nodes', []))
        page = r.get('pageInfo', {})
        if not page.get('hasNextPage'):
            break
        cursor = page.get('endCursor')
    return total, stars, forks


def get_contributions_for_year(token: str, username: str, year: int) -> tuple[int, int, int]:
    data = graphql(token, """
        query ($login: String!, $from: DateTime!, $to: DateTime!) {
            user(login: $login) {
                contributionsCollection(from: $from, to: $to) {
                    totalCommitContributions
                    totalPullRequestReviewContributions
                    contributionCalendar {
                        totalContributions
                    }
                }
            }
        }""", {'login': username,
               'from': f'{year}-01-01T00:00:00Z',
               'to':   f'{year}-12-31T23:59:59Z'})
    collection = (data.get('user', {})
                      .get('contributionsCollection', {}))
    return (
        collection.get('totalCommitContributions', 0),
        collection.get('totalPullRequestReviewContributions', 0),
        collection.get('contributionCalendar', {}).get('totalContributions', 0),
    )


def get_contribution_days_for_year(token: str, username: str, year: int) -> list[tuple[str, int]]:
    data = graphql(token, """
        query ($login: String!, $from: DateTime!, $to: DateTime!) {
            user(login: $login) {
                contributionsCollection(from: $from, to: $to) {
                    contributionCalendar {
                        weeks {
                            contributionDays {
                                contributionCount
                                date
                            }
                        }
                    }
                }
            }
        }""", {'login': username,
               'from': f'{year}-01-01T00:00:00Z',
               'to':   f'{year}-12-31T23:59:59Z'})
    weeks = (data.get('user', {})
                 .get('contributionsCollection', {})
                 .get('contributionCalendar', {})
                 .get('weeks', []))
    return sorted(
        [(d['date'], d['contributionCount']) for w in weeks for d in w.get('contributionDays', [])],
        key=lambda x: x[0]
    )


def get_streak(token: str, username: str, creation_year: int) -> tuple[int, int]:
    days = []
    current_year = datetime.datetime.now(datetime.timezone.utc).year
    for year in range(creation_year, current_year + 1):
        try:
            days.extend(get_contribution_days_for_year(token, username, year))
        except Exception as e:
            print(f'  Warning (streak {year}): {e}', file=sys.stderr)
    days.sort(key=lambda x: x[0])
    longest = current_run = 0
    for _, count in days:
        if count > 0:
            current_run += 1
            longest = max(longest, current_run)
        else:
            current_run = 0
    today = datetime.date.today().isoformat()
    days_to_check = [(d, c) for d, c in days if d <= today]
    if days_to_check and days_to_check[-1][0] == today and days_to_check[-1][1] == 0:
        days_to_check = days_to_check[:-1]
    current = 0
    for _, count in reversed(days_to_check):
        if count > 0:
            current += 1
        else:
            break
    return current, longest


def get_all_contributions(token: str, username: str, creation_year: int) -> tuple[int, int, int]:
    commits = reviews = total_contribs = 0
    current_year = datetime.datetime.now(datetime.timezone.utc).year
    for year in range(creation_year, current_year + 1):
        try:
            year_commits, year_reviews, year_total = get_contributions_for_year(token, username, year)
            commits += year_commits
            reviews += year_reviews
            total_contribs += year_total
        except Exception as e:
            print(f'  Warning (contributions {year}): {e}', file=sys.stderr)
    return commits, reviews, total_contribs


def get_loc(token: str, username: str) -> tuple[int, int, int]:
    repos = []
    cursor = None
    while True:
        data = graphql(token, """
            query ($login: String!, $cursor: String) {
                user(login: $login) {
                    repositories(first: 100, after: $cursor,
                                 ownerAffiliations: [OWNER, ORGANIZATION_MEMBER], isFork: false) {
                        nodes { nameWithOwner isEmpty defaultBranchRef { name } }
                        pageInfo { hasNextPage endCursor }
                    }
                }
            }""", {'login': username, 'cursor': cursor})
        rd = data.get('user', {}).get('repositories', {})
        for n in rd.get('nodes', []):
            if not n.get('isEmpty') and n.get('defaultBranchRef'):
                repos.append(n['nameWithOwner'])
        page = rd.get('pageInfo', {})
        if not page.get('hasNextPage'):
            break
        cursor = page.get('endCursor')

    commit_q = """
        query ($owner: String!, $name: String!, $cursor: String) {
            repository(owner: $owner, name: $name) {
                defaultBranchRef {
                    target {
                        ... on Commit {
                            history(first: 100, after: $cursor) {
                                nodes {
                                    additions deletions messageHeadline
                                    author { user { login } }
                                }
                                pageInfo { hasNextPage endCursor }
                            }
                        }
                    }
                }
            }
        }"""
    add, delete = 0, 0
    for repo in repos:
        owner, name = repo.split('/', 1)
        is_own_repo = owner.lower() == username.lower()
        cursor = None
        try:
            while True:
                data = graphql(token, commit_q,
                               {'owner': owner, 'name': name, 'cursor': cursor})
                history = (data.get('repository', {})
                               .get('defaultBranchRef', {})
                               .get('target', {})
                               .get('history', {}))
                for c in history.get('nodes', []):
                    if c.get('messageHeadline', '') == 'chore: update metadata backup':
                        continue
                    login = ((c.get('author') or {}).get('user') or {}).get('login', '')
                    if login.lower() == username.lower() or (is_own_repo and not login):
                        add    += c.get('additions', 0)
                        delete += c.get('deletions', 0)
                page = history.get('pageInfo', {})
                if not page.get('hasNextPage'):
                    break
                cursor = page.get('endCursor')
        except Exception as e:
            print(f'  Warning (LOC {repo}): {e}', file=sys.stderr)
    return add, delete, add - delete

# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def fmt(n: int) -> str:
    return f'{n:,}'


def fmt_uptime(created_at: str) -> str:
    created = datetime.date.fromisoformat(created_at[:10])
    today = datetime.date.today()
    delta = relativedelta(today, created)
    days = (today - (created + relativedelta(years=delta.years))).days
    return f'{delta.years}y {days}d'


def pad_dots(label: str, value: str, width: int = LINE_WIDTH) -> str:
    n = width - 2 - len(label) - 2 - 1 - len(str(value))
    return '.' * max(1, n)

# ---------------------------------------------------------------------------
# SVG fragment builders
# ---------------------------------------------------------------------------

def cc(t: str)  -> str: return f'<tspan class="cc">{esc(t)}</tspan>'
def key(t: str) -> str: return f'<tspan class="key">{esc(t)}</tspan>'
def val(t: str) -> str: return f'<tspan class="value">{esc(t)}</tspan>'

def trow(y: int, content: str) -> str:
    return f'    <tspan x="{STATS_X}" y="{y}">{content}</tspan>'

def info_row(y: int, label: str, value: str) -> str:
    return trow(y, cc('. ') + key(label) + cc(f': {pad_dots(label, str(value))} ') + val(str(value)))

def section_header(y: int, title: str) -> str:
    hyphens = '-' * max(2, LINE_WIDTH - 2 - len(title) - 1)
    return trow(y, f'- {title} {hyphens}')

def blank(y: int) -> str:
    return trow(y, '')

PIPE_LEFT = 36

def dual_row(y: int, lbl1: str, v1: str, lbl2: str, v2: str) -> str:
    d1 = max(1, PIPE_LEFT - 5 - len(lbl1) - len(v1))
    d2 = max(1, LINE_WIDTH - PIPE_LEFT - 6 - len(lbl2) - len(v2))
    return trow(y,
        cc('. ') + key(lbl1) + cc(f': {"."*d1} ') + val(v1) +
        cc(' | ') + key(lbl2) + cc(f': {"."*d2} ') + val(v2))

RIGHT_BUDGET = LINE_WIDTH - PIPE_LEFT - 3

def brace_inner_len(detail_lbl: str, detail_val: str) -> int:
    return len(f'{detail_lbl}: {detail_val}')

def brace_col_range(lbl2: str, v2_main: str, detail_lbl: str, detail_val: str) -> tuple[int, int]:
    p_min = len(lbl2) + len(v2_main) + 5
    p_max = RIGHT_BUDGET - 2 - brace_inner_len(detail_lbl, detail_val)
    return p_min, p_max

def shared_brace_col(rows: list[tuple[str, str, str, str]]) -> int:
    return max(brace_col_range(*row)[0] for row in rows)

def dual_row_detail(y: int, lbl1: str, v1: str, lbl2: str, v2_main: str, detail_lbl: str, detail_val: str,
                    brace_col: int | None = None) -> str:
    p_min, p_max = brace_col_range(lbl2, v2_main, detail_lbl, detail_val)
    p = p_min if brace_col is None else max(p_min, min(brace_col, p_max))
    d2 = p - len(lbl2) - len(v2_main) - 4
    natural_inner = brace_inner_len(detail_lbl, detail_val)
    gap = max(0, (RIGHT_BUDGET - p - 2) - natural_inner)
    dots = '.' * gap
    d1 = max(1, PIPE_LEFT - 5 - len(lbl1) - len(v1))
    v2_svg = (f'<tspan class="value">{esc(v2_main)} {{'
              f'<tspan class="key">{esc(detail_lbl)}</tspan>: ' +
              (f'<tspan class="cc">{dots}</tspan>' if dots else '') +
              f'{esc(detail_val)}}}</tspan>')
    return trow(y,
        cc('. ') + key(lbl1) + cc(f': {"."*d1} ') + val(v1) +
        cc(' | ') + key(lbl2) + cc(f': {"."*d2} ') + v2_svg)

def contribs_repos_row(y: int, lbl1: str, v1: str, repos: int, contributed: int, brace_col: int | None = None) -> str:
    return dual_row_detail(y, lbl1, v1, 'Repos', fmt(repos), 'Contrib', fmt(contributed), brace_col=brace_col)

def loc_dual_row(y: int, total: int, add: int, delete: int) -> str:
    net_str = fmt(total)
    add_str = fmt(add)
    del_str = fmt(delete)
    d1 = max(1, PIPE_LEFT - 5 - len('Lines of Code') - len(net_str))
    right_chars = LINE_WIDTH - PIPE_LEFT - 3
    inner = f'{add_str}++, {del_str}--'
    total_pad = right_chars - 2 - len(inner)
    lp = ' ' * (total_pad // 2)
    rp = ' ' * (total_pad - total_pad // 2)
    rhs = (f'{{{lp}<tspan class="addColor">{esc(add_str)}</tspan>++, '
           f'<tspan class="delColor">{esc(del_str)}</tspan>--{rp}}}')
    return trow(y,
        cc('. ') + key('Lines of Code') + cc(f': {"."*d1} ') + val(net_str) +
        cc(' | ') + rhs)

# ---------------------------------------------------------------------------
# SVG builder
# ---------------------------------------------------------------------------

def build_svg(
    ascii_rows: list[str],
    repos: int, contributed: int, stars: int, forks: int,
    commits: int, followers: int,
    prs: int, issues: int, reviews: int, gists: int,
    total_contribs: int, uptime: str,
    loc_total: int, loc_add: int, loc_del: int,
    current_streak: int, longest_streak: int,
    mode: str = 'adaptive',
) -> str:

    if mode == 'dark':
        base_palette = DARK
        media_override = ""
    elif mode == 'light':
        base_palette = LIGHT
        media_override = ""
    else:  # adaptive
        base_palette = DARK
        media_override = f"""
      @media (prefers-color-scheme: light) {{
        .bg        {{ fill: {LIGHT['bg']};     }}
        .fg        {{ fill: {LIGHT['text']};   }}
        .key       {{ fill: {LIGHT['key']};    }}
        .value     {{ fill: {LIGHT['value']};  }}
        .addColor {{ fill: {LIGHT['add']};    }}
        .delColor {{ fill: {LIGHT['delete']}; }}
        .cc        {{ fill: {LIGHT['dots']};   }}
      }}"""

    style = f"""
      @font-face {{
        src: local('Consolas'), local('Consolas Bold');
        font-family: 'ConsolasFallback';
        font-display: swap;
        size-adjust: 109%;
      }}
      .bg        {{ fill: {base_palette['bg']};     }}
      .fg        {{ fill: {base_palette['text']};   }}
      .key       {{ fill: {base_palette['key']};    }}
      .value     {{ fill: {base_palette['value']};  }}
      .addColor {{ fill: {base_palette['add']};    }}
      .delColor {{ fill: {base_palette['delete']}; }}
      .cc        {{ fill: {base_palette['dots']};   }}
      text, tspan {{ white-space: pre; }}{media_override}
    """

    ascii_tspans = [
        f'    <tspan x="{ASCII_X}" y="{ROW_START + ROW_STEP + 10 + ASCII_Y_OFFSET + i * ROW_STEP}">{esc(line)}</tspan>'
        for i, line in enumerate(ascii_rows)
    ]

    Y = [ROW_START + i * ROW_STEP for i in range(STATS_ROWS)]

    header_dashes = '-' * (LINE_WIDTH - len('damakerdev@github '))

    brace_col_target = shared_brace_col([
        ('Repos', fmt(repos), 'Contrib', fmt(contributed)),
        ('Streak', f'{fmt(current_streak)}d', 'Best', f'{fmt(longest_streak)}d'),
    ])

    stats_tspans = [
        trow(Y[0],  f'damakerdev@github {header_dashes}'),

        info_row(Y[1],  'Name',              'DaMakerDev -- the-maker-dev'),
        info_row(Y[2],  'Role',              'Electronics Engg. Student'),
        info_row(Y[3],  'Mode',              'Low-level C/C++, systems, games'),
        info_row(Y[4],  'Building',          'Blackbird Engine -> stockfish for baghchal'),
        info_row(Y[5],  'Learning',          'Compilers, terminal graphics, ascii cube'),
        info_row(Y[6],  'OS',                'Arch Linux + Hyprland'),

        blank(Y[7]),

        info_row(Y[8],  'Languages.Systems', 'C, C++, C#'),
        info_row(Y[9],  'Languages.Web',     'JS, TS, HTML, CSS, React'),
        info_row(Y[10], 'Languages.Real',    'English, Nepali, Hindi'),
        info_row(Y[11], 'Tools.Hardware',    'Arduino, Raspberry Pi, ESP32'),
        info_row(Y[12], 'Tools.Graphics',    'OpenGL, Blender, Figma'),
        info_row(Y[13], 'Engines',           'Godot, Unity, Phaser.js'),

        blank(Y[14]),

        info_row(Y[15], 'Current.Focus',    'Baghchal Engine (Stockfish / C++)'),
        info_row(Y[16], 'Goal',             'Mixed reality games -> games felt, not just played'),
        info_row(Y[17], 'Goal.Vision',      'Wii-style Motion & Sensor Games'),
        info_row(Y[18], 'Design',           'Figma, Dribbble'),
        info_row(Y[19], 'Hobbies.Software', 'simulate stuff && play games'),
        info_row(Y[20], 'Hobbies.Hardware', 'breaking broken hardware'),
        info_row(Y[21], 'Hobbies.Offline',  'Guitar, Writing, Trekking && touch grass'),

        blank(Y[22]),

        section_header(Y[23], 'Contact'),
        info_row(Y[24], 'Email',     'damakerdev@gmail.com'),
        info_row(Y[25], 'Site',      'damekstudios.com'),
        info_row(Y[26], 'Itch.io',   'damekstudios.itch.io'),
        info_row(Y[27], 'Blog',      'blog.damekstudios.com'),
        info_row(Y[28], 'Discord',   'damakerdev'),

        blank(Y[29]),

        section_header(Y[30], 'Git Stats'),
        dual_row(Y[31], 'Followers', fmt(followers),       'Stars',   fmt(stars)),
        dual_row(Y[32], 'Commits',   fmt(commits),         'PRs',     fmt(prs)),
        dual_row(Y[33], 'Issues',    fmt(issues),          'Reviews', fmt(reviews)),
        contribs_repos_row(Y[34], 'Contribs', fmt(total_contribs), repos, contributed, brace_col=brace_col_target),
        dual_row_detail(Y[35], 'Uptime', uptime, 'Streak', f'{fmt(current_streak)}d', 'Best', f'{fmt(longest_streak)}d', brace_col=brace_col_target),
        loc_dual_row(Y[36], loc_total, loc_add, loc_del),
        blank(Y[37]),
    ]

    ascii_block = '\n'.join(ascii_tspans)
    stats_block = '\n'.join(stats_tspans)

    return f"""<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg"
     font-family="ConsolasFallback,Consolas,monospace"
     width="{SVG_WIDTH}px" height="{SVG_HEIGHT}px"
     font-size="16px">
  <defs><style>{style}  </style></defs>
  <rect width="{SVG_WIDTH}px" height="{SVG_HEIGHT}px" class="bg" rx="15"/>
  <text x="{ASCII_X}" y="{ROW_START}" class="fg" font-size="{ASCII_FONT_SIZE}px"
        xml:space="preserve" style="white-space:pre;">
{ascii_block}
  </text>
  <text x="{STATS_X}" y="{ROW_START}" class="fg" style="white-space:pre;">
{stats_block}
  </text>
</svg>"""

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    token = os.environ.get('ACCESS_TOKEN', '').strip()
    if not token:
        print('ERROR: ACCESS_TOKEN environment variable is not set.', file=sys.stderr)
        sys.exit(1)

    contrib_token = os.environ.get('CONTRIB_TOKEN', '').strip() or token
    username = os.environ.get('USER_NAME', USERNAME)

    print('Loading ASCII art...')
    ascii_rows = load_ascii_art(ASCII_ART_PATH)

    print('Fetching GitHub stats...')
    followers, prs, contributed, issues, gists, creation_year, created_at = get_user_info(token, username)
    repos, stars, forks = get_repos_stars_and_forks(token, username)
    commits, reviews, total_contribs = get_all_contributions(contrib_token, username, creation_year)
    current_streak, longest_streak = get_streak(contrib_token, username, creation_year)
    loc_add, loc_del, loc_total = get_loc(token, username)
    uptime = fmt_uptime(created_at)

    print('Generating SVGs...')
    base_dir = os.path.dirname(__file__) or '.'

    adaptive_svg = build_svg(
        ascii_rows, repos, contributed, stars, forks, commits, followers,
        prs, issues, reviews, gists, total_contribs, uptime, loc_total,
        loc_add, loc_del, current_streak, longest_streak, mode='adaptive'
    )
    with open(os.path.join(base_dir, 'profile.svg'), 'w', encoding='utf-8') as f:
        f.write(adaptive_svg)

    dark_svg = build_svg(
        ascii_rows, repos, contributed, stars, forks, commits, followers,
        prs, issues, reviews, gists, total_contribs, uptime, loc_total,
        loc_add, loc_del, current_streak, longest_streak, mode='dark'
    )
    with open(os.path.join(base_dir, 'profile-dark.svg'), 'w', encoding='utf-8') as f:
        f.write(dark_svg)

    light_svg = build_svg(
        ascii_rows, repos, contributed, stars, forks, commits, followers,
        prs, issues, reviews, gists, total_contribs, uptime, loc_total,
        loc_add, loc_del, current_streak, longest_streak, mode='light'
    )
    with open(os.path.join(base_dir, 'profile-light.svg'), 'w', encoding='utf-8') as f:
        f.write(light_svg)

    print('Successfully generated profile.svg, profile-dark.svg, and profile-light.svg!')


if __name__ == '__main__':
    main()
