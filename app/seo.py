"""SEO (Search Engine Optimization) utilities for Splittchen.

This module provides utilities for generating SEO meta tags, structured data,
and other search engine optimization content. All features are controlled by
configuration flags and can be disabled by setting SEO_ENABLED=false in the
environment.

This allows deployment flexibility: your deployment can enable full SEO
optimization while other deployments remain unaffected.
"""

from typing import Dict, Any, Optional
from urllib.parse import urljoin


def get_seo_meta_tags(
    title: str,
    description: str,
    keywords: Optional[str] = None,
    image_url: Optional[str] = None,
    url: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate SEO meta tag data for a page.
    
    Args:
        title: Page title
        description: Page meta description
        keywords: Comma-separated keywords
        image_url: Open Graph image URL
        url: Canonical URL
        config: Application config dictionary
    
    Returns:
        Dictionary with SEO meta data
    
    Example:
        meta = get_seo_meta_tags(
            title="Create Expense Group",
            description="Split expenses with friends",
            config=app.config
        )
    """
    if not config or not config.get('SEO_ENABLED'):
        return {}
    
    meta = {
        'title': title,
        'description': description,
    }
    
    if keywords:
        meta['keywords'] = keywords
    
    # Open Graph (Facebook, LinkedIn, etc.)
    meta['og'] = {
        'title': title,
        'description': description,
        'type': 'website',
    }
    
    if image_url:
        meta['og']['image'] = image_url
    
    if url:
        meta['og']['url'] = url
    
    # Twitter Card
    meta['twitter'] = {
        'card': 'summary_large_image',
        'title': title,
        'description': description,
    }
    
    if image_url:
        meta['twitter']['image'] = image_url
    
    return meta


def get_structured_data_organization(
    site_name: str,
    description: str,
    base_url: str,
    logo_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate Organization schema.org structured data (JSON-LD).
    
    This helps search engines understand your website's identity and purpose.
    
    Args:
        site_name: Name of the website
        description: Organization description
        base_url: Base URL of the website
        logo_url: URL to organization logo
    
    Returns:
        Dictionary formatted as JSON-LD schema
    """
    schema = {
        '@context': 'https://schema.org',
        '@type': 'Organization',
        'name': site_name,
        'description': description,
        'url': base_url,
        'sameAs': [
            'https://github.com/splittchen/splittchen',
        ],
    }
    
    if logo_url:
        schema['logo'] = {
            '@type': 'ImageObject',
            'url': logo_url,
            'width': 200,
            'height': 200,
        }
    
    return schema


def get_structured_data_software_application(
    site_name: str,
    description: str,
    base_url: str,
) -> Dict[str, Any]:
    """Generate SoftwareApplication schema.org structured data (JSON-LD).
    
    This helps search engines classify your app correctly.
    
    Args:
        site_name: Name of the application
        description: Application description
        base_url: Base URL of the application
    
    Returns:
        Dictionary formatted as JSON-LD schema
    """
    return {
        '@context': 'https://schema.org',
        '@type': 'SoftwareApplication',
        'name': site_name,
        'description': description,
        'url': base_url,
        'applicationCategory': 'FinanceApplication',
        'offers': {
            '@type': 'Offer',
            'price': '0',
            'priceCurrency': 'USD',
        },
    }


def get_robots_txt(seo_enabled: bool, base_url: str) -> str:
    """Generate robots.txt content.
    
    When SEO is enabled, allows all crawlers. When disabled, blocks all crawlers
    to prevent indexing of a non-production instance.
    
    Args:
        seo_enabled: Whether SEO is enabled
        base_url: Base URL for Sitemap directive
    
    Returns:
        robots.txt content as string
    """
    if not seo_enabled:
        # Prevent indexing of non-SEO deployments
        return (
            "User-agent: *\n"
            "Disallow: /\n"
            "\n"
            "# This deployment has SEO_ENABLED=false\n"
            "# To enable search engine indexing, set SEO_ENABLED=true\n"
        )
    
    # Allow indexing when SEO is enabled
    sitemap_url = urljoin(base_url, '/sitemap.xml')
    return (
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        "# Disallow private group access tokens in URLs\n"
        "Disallow: /p/\n"
        "Disallow: /group/*/admin*\n"
        "\n"
        f"Sitemap: {sitemap_url}\n"
    )


def generate_sitemap_xml(
    groups: list,
    base_url: str,
) -> str:
    """Generate XML sitemap.
    
    Creates a sitemap with public URLs. Note: group pages are not included
    since they require tokens and are not meant to be indexed.
    
    Args:
        groups: List of Group objects (for future expansion)
        base_url: Base URL for absolute URLs
    
    Returns:
        XML sitemap as string
    """
    urls = [
        ('/', 'weekly'),  # Homepage
        ('/create-group', 'daily'),
        ('/join-group', 'daily'),
    ]
    
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    
    for path, changefreq in urls:
        url = urljoin(base_url, path)
        xml += f'  <url>\n'
        xml += f'    <loc>{url}</loc>\n'
        xml += f'    <changefreq>{changefreq}</changefreq>\n'
        xml += f'  </url>\n'
    
    xml += '</urlset>\n'
    return xml


def get_canonical_url(request_url: str, base_url: str) -> str:
    """Get canonical URL for a page.
    
    Canonical URLs help prevent duplicate content issues.
    
    Args:
        request_url: Current request URL
        base_url: Base URL to use instead of request URL
    
    Returns:
        Canonical URL
    """
    from urllib.parse import urlparse, urljoin
    
    path = urlparse(request_url).path
    return urljoin(base_url, path)
