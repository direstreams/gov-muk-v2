{% extends 'base.html' %}
{% block content %}
<section class="home-hero">
  <div class="gov-width">
    <div class="hero-topline">
      <a class="hero-brand" href="{{ url_for('home') }}">GOV<span>•</span>MUK</a>
      <div class="hero-mini-controls"><button type="button" class="menu-jump">⌄ Menu</button><span></span><button type="button" class="search-jump">⌕</button></div>
    </div>
    <div class="hero-copy-wrap">
      <h1>The best place to find government services and information</h1>
      <form class="hero-search" action="{{ url_for('search') }}" method="get">
        <label for="home-q">Search</label>
        <div><input id="home-q" name="q" aria-label="Search GOV.MUK"><button aria-label="Search">⌕</button></div>
      </form>
    </div>
  </div>
</section>
<section class="content-section popular-home">
  <div class="gov-width">
    <h2 class="section-title">Popular on GOV.MUK</h2>
    <div class="popular-grid">
      <a href="{{ url_for('travel') }}"><h3>Foreign travel advice</h3><p>View current security and conflict notices.</p></a>
      <a href="{{ url_for('documents') }}"><h3>Government publications</h3><p>Open official roleplay documents and statements.</p></a>
      <a href="{{ url_for('leadership') }}"><h3>Government and leadership</h3><p>View the Prime Minister and senior ministers.</p></a>
      <a href="{{ url_for('mod') }}"><h3>Defence careers</h3><p>Apply to 42 Commando or 856 Support Unit.</p></a>
      <a href="{{ url_for('bank') }}"><h3>Bank of MUK</h3><p>Access an administrator-issued citizen account.</p></a>
      <a href="{{ url_for('markets') }}"><h3>MUK Exchange</h3><p>Trade fictional shares using existing virtual credits.</p></a>
    </div>
  </div>
</section>
<section class="latest-news-section">
  <div class="gov-width">
    <p class="eyebrow dark">Latest update</p>
    <h2 class="section-title">{{ announcement_title }}</h2>
    <article class="latest-news-card">
      <img src="{{ url_for('static',filename='latest-mod-update.png') }}" alt="Military personnel featured in the latest Ministry of Defence update">
      <div>
        <span class="news-department">Ministry of Defence</span>
        <p class="news-date">Published 1 August 2026</p>
        <p>{{ announcement_text }}</p>
        <p>The Ministry will continue to review developments and publish further roleplay updates through official channels.</p>
        <a class="news-link" href="{{ url_for('mod') }}">Read the full Ministry of Defence update</a>
      </div>
    </article>
  </div>
</section>
{% endblock %}