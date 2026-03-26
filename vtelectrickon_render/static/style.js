function addToCart(id) {
    fetch("/order", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({id: id})
    })
    .then(res => res.json())
    .then(data => {
        alert(data.message);
        location.reload();
    });
}
