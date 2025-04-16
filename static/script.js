function startOrder() {
  fetch('/api/start-order', { method: 'POST' })
    .then(res => res.json())
    .then(data => {
      if (data.orderId) {
        localStorage.setItem('order_id', data.orderId);
        window.location.href = "/orders";
      } else {
        alert("Could not start order. Try again.");
      }
    })
    .catch(err => {
      console.error("Start order failed:", err);
      alert("Something went wrong. Try again.");
    });
}

// Optional: call this only after placing an order
function submitOrderSummary(selectedItemsArray) {
  const cid = localStorage.getItem('cid');
  const order_id = localStorage.getItem('order_id');

  const orderData = {
    cid: cid ? parseInt(cid) : null,
    order_id: order_id ? parseInt(order_id) : null,
    orderData: {
      selectedItems: selectedItemsArray
    }
  };

  fetch('/api/order-summary', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(orderData)
  })
    .then(response => {
      if (!response.ok) {
        throw new Error("Failed to save order summary");
      }
      return response.json();
    })
    .then(data => {
      console.log("Order summary response:", data);
    })
    .catch(error => {
      console.error("Error submitting order summary:", error);
    });
}

// Load rewards
fetch('/get_rewards')
  .then(response => response.json())
  .then(data => {
    console.log(data);
    data.forEach(reward => {
      const rewardElement = document.createElement('div');
      rewardElement.textContent = `${reward.pointsEarned} points - ${reward.rewardType}`;
      document.getElementById('rewards-container').appendChild(rewardElement);
    });
  })
  .catch(error => console.error('Error fetching rewards:', error));
