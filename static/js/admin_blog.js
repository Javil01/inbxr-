/* ══════════════════════════════════════════════════════
   INBXR — Admin Blog Manager + Editor JS
   ══════════════════════════════════════════════════════ */

(function() {
  'use strict';

  // ── Helpers ──
  function esc(s) {
    return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  function shortDate(d) {
    if (!d) return '';
    try {
      var dt = new Date(d.indexOf('Z') > -1 ? d : d + 'Z');
      return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    } catch(e) { return ''; }
  }

  // ═══════════════════════════════════════════════════
  // BLOG LIST PAGE (admin_blog.html)
  // ═══════════════════════════════════════════════════

  var abBody = document.getElementById('abBody');

  // Only run list-page code if the table body exists
  if (abBody && !document.getElementById('postTitle')) {

    function loadPosts() {
      fetch('/admin/api/blog/posts')
        .then(function(r) { return r.json(); })
        .then(function(data) {
          var posts = data.posts || [];
          var published = 0, drafts = 0;
          posts.forEach(function(p) {
            if (p.status === 'published') published++;
            else drafts++;
          });

          document.getElementById('statTotal').textContent = posts.length;
          document.getElementById('statPublished').textContent = published;
          document.getElementById('statDrafts').textContent = drafts;

          if (!posts.length) {
            abBody.innerHTML = '<tr><td colspan="5" class="ab-empty">No posts yet. Create your first post!</td></tr>';
            return;
          }

          var html = '';
          posts.forEach(function(p) {
            html += '<tr>' +
              '<td class="ab-title-cell">' + esc(p.title) + '</td>' +
              '<td><span class="ab-status ab-status--' + p.status + '">' + p.status + '</span></td>' +
              '<td>' + esc(p.category_name || '—') + '</td>' +
              '<td class="ab-date">' + shortDate(p.published_at || p.created_at) + '</td>' +
              '<td class="ab-actions">' +
                '<a href="/admin/blog/edit/' + p.id + '">Edit</a>' +
                '<button class="ab-btn--red" onclick="deletePost(' + p.id + ')">Delete</button>' +
              '</td>' +
            '</tr>';
          });
          abBody.innerHTML = html;
        })
        .catch(function() {
          abBody.innerHTML = '<tr><td colspan="5" class="ab-empty">Failed to load posts.</td></tr>';
        });
    }

    window.deletePost = function(id) {
      if (!confirm('Delete this post? This cannot be undone.')) return;
      fetch('/admin/api/blog/posts/' + id, { method: 'DELETE' })
        .then(function(r) { return r.json(); })
        .then(function(d) {
          if (d.ok) loadPosts();
          else alert(d.error || 'Failed to delete');
        })
        .catch(function() { alert('Network error'); });
    };

    function loadCategories() {
      fetch('/admin/api/blog/categories')
        .then(function(r) { return r.json(); })
        .then(function(data) {
          var cats = data.categories || [];
          var list = document.getElementById('catList');
          if (!cats.length) {
            list.innerHTML = '<span style="font-size:0.78rem; color:var(--text-3);">No categories yet.</span>';
            return;
          }
          var html = '';
          cats.forEach(function(c) {
            html += '<span class="ab-cat-chip">' + esc(c.name) +
              '<button onclick="deleteCategory(' + c.id + ')" title="Delete">&times;</button>' +
            '</span>';
          });
          list.innerHTML = html;
        });
    }

    window.addCategory = function() {
      var input = document.getElementById('catName');
      var name = input.value.trim();
      if (!name) return;
      fetch('/admin/api/blog/categories', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: name })
      })
      .then(function(r) { return r.json(); })
      .then(function(d) {
        if (d.ok) { input.value = ''; loadCategories(); }
        else alert(d.error || 'Failed');
      });
    };

    window.deleteCategory = function(id) {
      if (!confirm('Delete this category?')) return;
      fetch('/admin/api/blog/categories/' + id, { method: 'DELETE' })
        .then(function(r) { return r.json(); })
        .then(function(d) {
          if (d.ok) loadCategories();
          else alert(d.error || 'Failed');
        });
    };

    // Allow Enter key in category input
    document.getElementById('catName').addEventListener('keydown', function(e) {
      if (e.key === 'Enter') { e.preventDefault(); addCategory(); }
    });

    loadPosts();
    loadCategories();
  }


  // ═══════════════════════════════════════════════════
  // BLOG EDITOR PAGE (admin_blog_editor.html)
  // ═══════════════════════════════════════════════════

  var titleInput = document.getElementById('postTitle');

  if (titleInput) {

    var currentStatus = (document.getElementById('postStatus') || {}).value || 'draft';

    // Load categories into dropdown
    function loadEditorCategories() {
      fetch('/admin/api/blog/categories')
        .then(function(r) { return r.json(); })
        .then(function(data) {
          var sel = document.getElementById('postCategory');
          var cats = data.categories || [];
          cats.forEach(function(c) {
            var opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = c.name;
            if (typeof POST_CATEGORY !== 'undefined' && String(c.id) === String(POST_CATEGORY)) {
              opt.selected = true;
            }
            sel.appendChild(opt);
          });
        });
    }

    // Auto-generate slug from title
    window.autoSlug = function() {
      var title = titleInput.value;
      var slug = title.toLowerCase()
        .replace(/[^a-z0-9\s-]/g, '')
        .replace(/\s+/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '');
      document.getElementById('postSlug').value = slug;
      calculateReadTime();
    };

    // Set status
    window.setStatus = function(status) {
      currentStatus = status;
      document.getElementById('postStatus').value = status;
      var draftBtn = document.getElementById('statusDraft');
      var pubBtn = document.getElementById('statusPublished');
      if (status === 'draft') {
        draftBtn.style.background = 'rgba(245,158,11,0.15)';
        draftBtn.style.color = '#f59e0b';
        draftBtn.style.borderColor = 'rgba(245,158,11,0.3)';
        pubBtn.style.opacity = '0.5';
        pubBtn.style.background = '#16a34a';
      } else {
        pubBtn.style.opacity = '1';
        draftBtn.style.background = 'transparent';
        draftBtn.style.color = '#94a3b8';
        draftBtn.style.borderColor = 'rgba(255,255,255,0.1)';
      }
    };

    // Save post
    window.savePost = function(status) {
      if (status) {
        currentStatus = status;
        document.getElementById('postStatus').value = status;
      }

      var payload = {
        title: titleInput.value.trim(),
        slug: document.getElementById('postSlug').value.trim(),
        content: document.getElementById('postContent').value,
        status: currentStatus,
        category_id: document.getElementById('postCategory').value || null,
        tags: document.getElementById('postTags').value.trim(),
        featured_image: document.getElementById('postImage').value.trim(),
        meta_title: document.getElementById('postMetaTitle').value.trim(),
        meta_description: document.getElementById('postMetaDesc').value.trim(),
        target_keyword: document.getElementById('postKeyword').value.trim(),
        og_image: document.getElementById('postOgImage').value.trim()
      };

      if (!payload.title) { alert('Title is required'); return; }
      if (!payload.slug) { alert('Slug is required'); return; }

      var method = (typeof POST_ID !== 'undefined' && POST_ID) ? 'PUT' : 'POST';
      var url = (typeof POST_ID !== 'undefined' && POST_ID)
        ? '/admin/api/blog/posts/' + POST_ID
        : '/admin/api/blog/posts';

      fetch(url, {
        method: method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      .then(function(r) { return r.json(); })
      .then(function(d) {
        if (d.ok) {
          if (!POST_ID && d.id) {
            // Redirect to edit page for newly created post
            window.location.href = '/admin/blog/edit/' + d.id;
          } else {
            // Show saved confirmation
            var btn = document.querySelector('.blog-editor__btn--' + (currentStatus === 'published' ? 'publish' : 'draft'));
            if (btn) {
              var origText = btn.textContent;
              btn.textContent = 'Saved!';
              setTimeout(function() { btn.textContent = origText; }, 1500);
            }
          }
        } else {
          alert(d.error || 'Failed to save');
        }
      })
      .catch(function() { alert('Network error'); });
    };

    // Delete post (editor page)
    window.deletePost = function() {
      if (typeof POST_ID === 'undefined' || !POST_ID) return;
      if (!confirm('Delete this post? This cannot be undone.')) return;
      fetch('/admin/api/blog/posts/' + POST_ID, { method: 'DELETE' })
        .then(function(r) { return r.json(); })
        .then(function(d) {
          if (d.ok) window.location.href = '/admin/blog';
          else alert(d.error || 'Failed');
        });
    };

    // Generate with AI
    window.generateWithAI = function() {
      var topic = document.getElementById('aiTopic').value.trim();
      var keyword = document.getElementById('aiKeyword').value.trim();
      if (!topic) { alert('Enter a topic first'); return; }

      var btn = document.getElementById('aiGenerateBtn');
      var loading = document.getElementById('aiLoading');
      btn.disabled = true;
      btn.style.opacity = '0.5';
      loading.style.display = 'block';

      fetch('/admin/api/blog/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: topic, keyword: keyword })
      })
      .then(function(r) { return r.json(); })
      .then(function(d) {
        btn.disabled = false;
        btn.style.opacity = '1';
        loading.style.display = 'none';

        if (d.error) { alert(d.error); return; }

        // Populate fields
        if (d.title) { titleInput.value = d.title; autoSlug(); }
        if (d.content) document.getElementById('postContent').value = d.content;
        if (d.meta_title) document.getElementById('postMetaTitle').value = d.meta_title;
        if (d.meta_description) document.getElementById('postMetaDesc').value = d.meta_description;
        if (d.excerpt) { /* can be used if needed */ }
        if (keyword) document.getElementById('postKeyword').value = keyword;

        // Update char counts
        updateCharCount(document.getElementById('postMetaTitle'), 'metaTitleCount', 60);
        updateCharCount(document.getElementById('postMetaDesc'), 'metaDescCount', 160);
        calculateReadTime();
      })
      .catch(function() {
        btn.disabled = false;
        btn.style.opacity = '1';
        loading.style.display = 'none';
        alert('Failed to generate. Check API connection.');
      });
    };

    // Toggle preview
    window.togglePreview = function() {
      var preview = document.getElementById('previewPane');
      var textarea = document.getElementById('postContent');
      if (preview.style.display === 'none') {
        preview.innerHTML = textarea.value;
        preview.style.display = 'block';
        textarea.style.display = 'none';
      } else {
        preview.style.display = 'none';
        textarea.style.display = 'block';
      }
    };

    // Character counter
    window.updateCharCount = function(input, counterId, target) {
      var el = document.getElementById(counterId);
      if (!el || !input) return;
      var len = input.value.length;
      el.textContent = len + ' / ' + target;
      if (len > target) {
        el.classList.add('blog-editor__char-count--over');
      } else {
        el.classList.remove('blog-editor__char-count--over');
      }
    };

    // Calculate read time
    window.calculateReadTime = function() {
      var content = document.getElementById('postContent').value;
      var text = content.replace(/<[^>]*>/g, '').trim();
      var words = text ? text.split(/\s+/).length : 0;
      var readTime = Math.max(1, Math.ceil(words / 200));
      var rtEl = document.getElementById('readTimeDisplay');
      var wcEl = document.getElementById('wordCountDisplay');
      if (rtEl) rtEl.textContent = readTime + ' min';
      if (wcEl) wcEl.textContent = words;
    };

    // Content textarea change listener for read time
    var contentArea = document.getElementById('postContent');
    if (contentArea) {
      contentArea.addEventListener('input', calculateReadTime);
    }

    // Upload featured image
    window.uploadImage = function(input) {
      var file = input.files[0];
      if (!file) return;
      var uploading = document.getElementById('imageUploading');
      uploading.style.display = 'block';

      var formData = new FormData();
      formData.append('file', file);

      fetch('/admin/api/media/upload', {
        method: 'POST',
        body: formData
      })
      .then(function(r) { return r.json(); })
      .then(function(d) {
        uploading.style.display = 'none';
        if (d.ok && d.url) {
          document.getElementById('postImage').value = d.url;
          document.getElementById('imagePreviewImg').src = d.url;
          document.getElementById('imagePreview').style.display = 'block';
        } else {
          alert(d.error || 'Upload failed');
        }
      })
      .catch(function() {
        uploading.style.display = 'none';
        alert('Upload failed');
      });

      input.value = '';
    };

    // Remove featured image
    window.removeImage = function() {
      document.getElementById('postImage').value = '';
      document.getElementById('imagePreview').style.display = 'none';
      document.getElementById('imagePreviewImg').src = '';
    };

    // Newsletter rewrite
    window.rewriteForNewsletter = function() {
      var btn = document.getElementById('nlBtn');
      var loading = document.getElementById('nlLoading');
      btn.disabled = true;
      btn.style.opacity = '0.5';
      loading.style.display = 'block';

      var payload = {};
      if (typeof POST_ID !== 'undefined' && POST_ID) {
        payload.post_id = POST_ID;
      }
      // Also send current editor content in case it's been modified
      payload.title = titleInput.value.trim();
      payload.content = document.getElementById('postContent').value;

      fetch('/admin/api/blog/newsletter', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      .then(function(r) { return r.json(); })
      .then(function(d) {
        btn.disabled = false;
        btn.style.opacity = '1';
        loading.style.display = 'none';

        if (!d.ok) { alert(d.error || 'Failed to rewrite'); return; }

        document.getElementById('nlSubject').value = d.subject || '';
        document.getElementById('nlPreview').value = d.preview_text || '';
        document.getElementById('nlBody').value = d.body || '';
        document.getElementById('nlRendered').style.display = 'none';
        document.getElementById('nlPreviewBtn').textContent = 'Preview';
        var modal = document.getElementById('nlModal');
        modal.style.display = 'flex';
      })
      .catch(function() {
        btn.disabled = false;
        btn.style.opacity = '1';
        loading.style.display = 'none';
        alert('Failed to rewrite. Check API connection.');
      });
    };

    window.closeNlModal = function() {
      document.getElementById('nlModal').style.display = 'none';
    };

    window.copyField = function(id) {
      var el = document.getElementById(id);
      var text = el.value || el.textContent;
      navigator.clipboard.writeText(text).then(function() {
        var btn = el.parentElement.querySelector('button[onclick*="copyField"]') ||
                  el.nextElementSibling;
        if (btn) {
          var orig = btn.textContent;
          btn.textContent = 'Copied!';
          setTimeout(function() { btn.textContent = orig; }, 1500);
        }
      });
    };

    window.toggleNlPreview = function() {
      var rendered = document.getElementById('nlRendered');
      var btn = document.getElementById('nlPreviewBtn');
      if (rendered.style.display === 'none') {
        rendered.innerHTML = document.getElementById('nlBody').value;
        rendered.style.display = 'block';
        btn.textContent = 'Hide Preview';
      } else {
        rendered.style.display = 'none';
        btn.textContent = 'Preview';
      }
    };

    // Close modal on backdrop click
    var nlModal = document.getElementById('nlModal');
    if (nlModal) {
      nlModal.addEventListener('click', function(e) {
        if (e.target === nlModal) closeNlModal();
      });
    }

    // Initialize
    loadEditorCategories();
    calculateReadTime();

    // Initialize char counts on page load
    setTimeout(function() {
      var mt = document.getElementById('postMetaTitle');
      var md = document.getElementById('postMetaDesc');
      if (mt && mt.value) updateCharCount(mt, 'metaTitleCount', 60);
      if (md && md.value) updateCharCount(md, 'metaDescCount', 160);
    }, 100);
  }

})();
