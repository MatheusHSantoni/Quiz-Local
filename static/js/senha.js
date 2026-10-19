document.addEventListener('click', function (event) {
  const botao = event.target.closest('[data-password-toggle]');
  if (!botao) return;
  const campo = document.getElementById(botao.dataset.passwordToggle);
  if (!campo) return;
  const exibindo = campo.type === 'text';
  campo.type = exibindo ? 'password' : 'text';
  botao.textContent = exibindo ? 'Exibir' : 'Ocultar';
  botao.setAttribute('aria-label', exibindo ? 'Exibir senha' : 'Ocultar senha');
});
