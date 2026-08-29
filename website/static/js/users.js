(function () {
  const searchInput = document.getElementById("searchInput");
  const filterRole = document.getElementById("filterRole");
  const filterStatus = document.getElementById("filterStatus");
  const emptyState = document.getElementById("usersEmpty");
  const editForm = document.getElementById("editForm");
  const resetForm = document.getElementById("resetPasswordForm");
  const passwordError = document.getElementById("error-message");
  let currentEditId = null;

  function postForm(url, data) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams(data),
    });
  }

  function applyUserFilters() {
    const query = (searchInput.value || "").trim().toLowerCase();
    const status = filterStatus.value;
    const role = filterRole.value;
    const cards = document.querySelectorAll(".user-card");
    let visible = 0;

    cards.forEach(function (card) {
      const textMatch = !query || (card.getAttribute("data-search") || "").indexOf(query) > -1;
      const statusMatch = !status || card.getAttribute("data-status") === status;
      const roleMatch = !role || card.getAttribute("data-role") === role;
      const show = textMatch && statusMatch && roleMatch;
      card.hidden = !show;
      if (show) {
        visible += 1;
      }
    });

    document.querySelectorAll(".user-group").forEach(function (group) {
      const anyVisible = Array.prototype.some.call(
        group.querySelectorAll(".user-card"),
        function (card) {
          return !card.hidden;
        }
      );
      group.hidden = !anyVisible;
    });

    if (emptyState) {
      emptyState.hidden = visible > 0;
    }
  }

  function openEdit(userId) {
    currentEditId = userId;
    postForm("/get_user", { user_id: userId })
      .then(function (response) {
        return response.json().then(function (data) {
          if (!response.ok) {
            throw new Error(data.error || "Could not load user.");
          }
          document.getElementById("edit_first_name").value = data.name_first || "";
          document.getElementById("edit_last_name").value = data.name_last || "";
          document.getElementById("edit_email").value = data.email || "";
          document.getElementById("edit_role").value = data.role || "client";
          document.getElementById("edit_date_birth").value = data.date_birth || "";
          document.getElementById("edit_address").value = data.address || "";
          bootstrap.Modal.getOrCreateInstance(document.getElementById("editModal")).show();
        });
      })
      .catch(function (error) {
        window.alert(error.message);
      });
  }

  function submitEdit(event) {
    event.preventDefault();
    postForm("/edit_user", {
      user_id: currentEditId,
      name_first: document.getElementById("edit_first_name").value,
      name_last: document.getElementById("edit_last_name").value,
      email: document.getElementById("edit_email").value,
      role: document.getElementById("edit_role").value,
      date_birth: document.getElementById("edit_date_birth").value,
      address: document.getElementById("edit_address").value,
    }).then(function (response) {
      if (response.ok) {
        window.location.reload();
        return;
      }
      return response.json().then(function (data) {
        window.alert(data.error || "Could not save user.");
      });
    });
  }

  function toggleStatus(button) {
    const name = button.getAttribute("data-name") || "this user";
    const status = Number(button.getAttribute("data-status"));
    const action = status === 1 ? "disable" : "enable";
    if (!window.confirm("Really " + action + " " + name + "?")) {
      return;
    }
    postForm("/status_change_user", { user_id: button.getAttribute("data-user-id") }).then(
      function (response) {
        if (response.ok) {
          window.location.reload();
          return;
        }
        return response.json().then(function (data) {
          window.alert(data.error || "Could not update status.");
        });
      }
    );
  }

  function openReset(userId) {
    currentEditId = userId;
    document.getElementById("newPassword").value = "";
    document.getElementById("confirmPassword").value = "";
    passwordError.hidden = true;
    bootstrap.Modal.getOrCreateInstance(document.getElementById("resetPasswordModal")).show();
  }

  function submitReset(event) {
    event.preventDefault();
    const password = document.getElementById("newPassword").value;
    const confirmPassword = document.getElementById("confirmPassword").value;
    if (password !== confirmPassword) {
      passwordError.textContent = "Passwords do not match.";
      passwordError.hidden = false;
      return;
    }
    postForm("/reset_password", {
      user_id: currentEditId,
      newPassword: password,
      confirmPassword: confirmPassword,
    }).then(function (response) {
      return response.json().then(function (data) {
        if (response.ok) {
          window.location.reload();
          return;
        }
        passwordError.textContent = data.error || "Could not reset password.";
        passwordError.hidden = false;
      });
    });
  }

  document.addEventListener("click", function (event) {
    const editBtn = event.target.closest(".js-edit-user");
    if (editBtn) {
      openEdit(editBtn.getAttribute("data-user-id"));
      return;
    }
    const toggleBtn = event.target.closest(".js-toggle-user");
    if (toggleBtn) {
      toggleStatus(toggleBtn);
      return;
    }
    const resetBtn = event.target.closest(".js-reset-user");
    if (resetBtn) {
      openReset(resetBtn.getAttribute("data-user-id"));
    }
  });

  if (searchInput) {
    searchInput.addEventListener("input", applyUserFilters);
  }
  if (filterRole) {
    filterRole.addEventListener("change", applyUserFilters);
  }
  if (filterStatus) {
    filterStatus.addEventListener("change", applyUserFilters);
  }
  if (editForm) {
    editForm.addEventListener("submit", submitEdit);
  }
  if (resetForm) {
    resetForm.addEventListener("submit", submitReset);
  }
})();
