# Thermal Control Pro v8.2 🌡️⚙️

Sistema de controle térmico de malha fechada desenvolvido para fins acadêmicos e laboratoriais. O projeto utiliza um controlador **PID (Proporcional, Integral e Derivativo)** implementado em um ecossistema **Python + Arduino**.

## 🚀 Funcionalidades

* **Controle PID em Tempo Real:** Ajuste dinâmico de ganhos ($K_p$, $K_i$, $K_d$) através da interface.
* **Três Modos de Operação:**
    * **Automático:** Controle completo de aquecimento e resfriamento.
    * **Só Aquecimento:** Trava de segurança que impede o acionamento da ventoinha.
    * **Só Ventilação:** Lâmpada mantida em potência constante enquanto o PID gerencia apenas o resfriamento.
* **Segurança e Estabilização:** * Validação de Setpoint (aviso para valores fora da faixa de 20°C a 40°C).
    * Bloqueio de inputs (intervalo e modo) após o início do controle.
    * Filtro de 2 segundos para estabilização do sensor no início da medição.
* **Exportação de Dados:** Geração de relatórios em **Excel (.xlsx)** e captura de gráfico em **PNG**.

## 🛠️ Tecnologias Utilizadas

* **Linguagem:** Python 3.12 (PyCharm IDE).
* **GUI:** CustomTkinter.
* **Gráficos:** Matplotlib (Plotagem em escala real).
* **Firmware:** C++/Arduino (Código na pasta `/firmware`).

## 📁 Estrutura do Projeto

* `v6.py`: Arquivo principal da interface Python.
* `/firmware`: Pasta contendo o código `.ino` para o Arduino.
* `requirements.txt`: Lista de dependências para instalação rápida.
* `logo.ico`: Ícone personalizado do software.
* `LICENSE`: Licença MIT de uso.

## 📝 Licença

Este projeto está sob a licença **MIT**. O software é fornecido "como está", sem garantias de qualquer tipo.

---

## ⚠️ AVISO DE ISENÇÃO DE RESPONSABILIDADE (DISCLAIMER)

Este software foi desenvolvido para fins didáticos e laboratoriais de baixa potência. O autor, ressalta que este sistema não deve ser aplicado em ambientes industriais reais ou máquinas cobertas pela **NR-12** sem as devidas adequações de hardware e redundâncias de segurança necessárias. O uso deste software em aplicações críticas é de inteira responsabilidade do usuário.

---

**Autor(es):** Alex Leão / Jedson Oliveira